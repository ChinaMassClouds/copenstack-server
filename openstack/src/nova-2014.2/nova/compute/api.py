# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Piston Cloud Computing, Inc.
# Copyright 2012-2013 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Handles all requests relating to compute resources (e.g. guest VMs,
networking and storage of VMs, and compute hosts on which they run)."""

import base64
import functools
import re
import string
import uuid

from oslo.config import cfg
from oslo.utils import units
import six

from nova import availability_zones
from nova import block_device
from nova.cells import opts as cells_opts
from nova.compute import flavors
from nova.compute import instance_actions
from nova.compute import power_state
from nova.compute import rpcapi as compute_rpcapi
from nova.compute import task_states
from nova.compute import utils as compute_utils
from nova.compute import vm_states
from nova.consoleauth import rpcapi as consoleauth_rpcapi
from nova import crypto
from nova.db import base
from nova import exception
from nova import hooks
from nova.i18n import _
from nova.i18n import _LE
from nova import image
from nova import keymgr
from nova import network
from nova.network import model as network_model
from nova.network.security_group import openstack_driver
from nova.network.security_group import security_group_base
from nova import notifications
from nova import objects
from nova.objects import base as obj_base
from nova.objects import quotas as quotas_obj
from nova.objects import security_group as security_group_obj
from nova.openstack.common import excutils
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging
from nova.openstack.common import strutils
from nova.openstack.common import timeutils
from nova.openstack.common import uuidutils
from nova.pci import pci_request
import nova.policy
from nova import quota
from nova import rpc
from nova import servicegroup
from nova import utils
from nova.virt import hardware
from nova import volume

LOG = logging.getLogger(__name__)

get_notifier = functools.partial(rpc.get_notifier, service='compute')
wrap_exception = functools.partial(exception.wrap_exception,
                                   get_notifier=get_notifier)

compute_opts = [
    cfg.BoolOpt('allow_resize_to_same_host',
                default=False,
                help='Allow destination machine to match source for resize. '
                     'Useful when testing in single-host environments.'),
    cfg.BoolOpt('allow_migrate_to_same_host',
                default=False,
                help='Allow migrate machine to the same host. '
                     'Useful when testing in single-host environments.'),
    cfg.StrOpt('default_schedule_zone',
               help='Availability zone to use when user doesn\'t specify one'),
    cfg.ListOpt('non_inheritable_image_properties',
                default=['cache_in_nova',
                         'bittorrent'],
                help='These are image properties which a snapshot should not'
                     ' inherit from an instance'),
    cfg.StrOpt('null_kernel',
               default='nokernel',
               help='Kernel image that indicates not to use a kernel, but to '
                    'use a raw disk image instead'),
    cfg.StrOpt('multi_instance_display_name_template',
               default='%(name)s-%(uuid)s',
               help='When creating multiple instances with a single request '
                    'using the os-multiple-create API extension, this '
                    'template will be used to build the display name for '
                    'each instance. The benefit is that the instances '
                    'end up with different hostnames. To restore legacy '
                    'behavior of every instance having the same name, set '
                    'this option to "%(name)s".  Valid keys for the '
                    'template are: name, uuid, count.'),
     cfg.IntOpt('max_local_block_devices',
                default=3,
                help='Maximum number of devices that will result '
                     'in a local image being created on the hypervisor node. '
                     'Setting this to 0 means nova will allow only '
                     'boot from volume. A negative number means unlimited.'),
]

ephemeral_storage_encryption_group = cfg.OptGroup(
    name='ephemeral_storage_encryption',
    title='Ephemeral storage encryption options')

ephemeral_storage_encryption_opts = [
    cfg.BoolOpt('enabled',
                default=False,
                help='Whether to encrypt ephemeral storage'),
    cfg.StrOpt('cipher',
               default='aes-xts-plain64',
               help='The cipher and mode to be used to encrypt ephemeral '
                    'storage. Which ciphers are available ciphers depends '
                    'on kernel support. See /proc/crypto for the list of '
                    'available options.'),
    cfg.IntOpt('key_size',
               default=512,
               help='The bit length of the encryption key to be used to '
                    'encrypt ephemeral storage (in XTS mode only half of '
                    'the bits are used for encryption key)')
]

CONF = cfg.CONF
CONF.register_opts(compute_opts)
CONF.register_group(ephemeral_storage_encryption_group)
CONF.register_opts(ephemeral_storage_encryption_opts,
                   group='ephemeral_storage_encryption')
CONF.import_opt('compute_topic', 'nova.compute.rpcapi')
CONF.import_opt('enable', 'nova.cells.opts', group='cells')
CONF.import_opt('default_ephemeral_format', 'nova.virt.driver')

MAX_USERDATA_SIZE = 65535
QUOTAS = quota.QUOTAS
RO_SECURITY_GROUPS = ['default']
VIDEO_RAM = 'hw_video:ram_max_mb'


def check_instance_state(vm_state=None, task_state=(None,),
                         must_have_launched=True):
    """Decorator to check VM and/or task state before entry to API functions.

    If the instance is in the wrong state, or has not been successfully
    started at least once the wrapper will raise an exception.
    """

    if vm_state is not None and not isinstance(vm_state, set):
        vm_state = set(vm_state)
    if task_state is not None and not isinstance(task_state, set):
        task_state = set(task_state)

    def outer(f):
        @functools.wraps(f)
        def inner(self, context, instance, *args, **kw):
            if vm_state is not None and instance['vm_state'] not in vm_state:
                raise exception.InstanceInvalidState(
                    attr='vm_state',
                    instance_uuid=instance['uuid'],
                    state=instance['vm_state'],
                    method=f.__name__)
            if (task_state is not None and
                    instance['task_state'] not in task_state):
                raise exception.InstanceInvalidState(
                    attr='task_state',
                    instance_uuid=instance['uuid'],
                    state=instance['task_state'],
                    method=f.__name__)
            if must_have_launched and not instance['launched_at']:
                raise exception.InstanceInvalidState(
                    attr=None,
                    not_launched=True,
                    instance_uuid=instance['uuid'],
                    state=instance['vm_state'],
                    method=f.__name__)

            return f(self, context, instance, *args, **kw)
        return inner
    return outer


def check_instance_host(function):
    @functools.wraps(function)
    def wrapped(self, context, instance, *args, **kwargs):
        if not instance['host']:
            raise exception.InstanceNotReady(instance_id=instance['uuid'])
        return function(self, context, instance, *args, **kwargs)
    return wrapped


def check_instance_lock(function):
    @functools.wraps(function)
    def inner(self, context, instance, *args, **kwargs):
        if instance['locked'] and not context.is_admin:
            raise exception.InstanceIsLocked(instance_uuid=instance['uuid'])
        return function(self, context, instance, *args, **kwargs)
    return inner


def policy_decorator(scope):
    """Check corresponding policy prior of wrapped method to execution."""
    def outer(func):
        @functools.wraps(func)
        def wrapped(self, context, target, *args, **kwargs):
            check_policy(context, func.__name__, target, scope)
            return func(self, context, target, *args, **kwargs)
        return wrapped
    return outer

wrap_check_policy = policy_decorator(scope='compute')
wrap_check_security_groups_policy = policy_decorator(
                                    scope='compute:security_groups')


def check_policy(context, action, target, scope='compute'):
    _action = '%s:%s' % (scope, action)
    nova.policy.enforce(context, _action, target)


def check_instance_cell(fn):
    def _wrapped(self, context, instance, *args, **kwargs):
        self._validate_cell(instance, fn.__name__)
        return fn(self, context, instance, *args, **kwargs)
    _wrapped.__name__ = fn.__name__
    return _wrapped


def _diff_dict(orig, new):
    """Return a dict describing how to change orig to new.  The keys
    correspond to values that have changed; the value will be a list
    of one or two elements.  The first element of the list will be
    either '+' or '-', indicating whether the key was updated or
    deleted; if the key was updated, the list will contain a second
    element, giving the updated value.
    """
    # Figure out what keys went away
    result = dict((k, ['-']) for k in set(orig.keys()) - set(new.keys()))
    # Compute the updates
    for key, value in new.items():
        if key not in orig or value != orig[key]:
            result[key] = ['+', value]
    return result


class API(base.Base):
    """API for interacting with the compute manager."""

    def __init__(self, image_api=None, network_api=None, volume_api=None,
                 security_group_api=None, **kwargs):
        self.image_api = image_api or image.API()
        self.network_api = network_api or network.API()
        self.volume_api = volume_api or volume.API()
        self.security_group_api = (security_group_api or
            openstack_driver.get_openstack_security_group_driver())
        self.consoleauth_rpcapi = consoleauth_rpcapi.ConsoleAuthAPI()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self._compute_task_api = None
        self.servicegroup_api = servicegroup.API()
        self.notifier = rpc.get_notifier('compute', CONF.host)
        if CONF.ephemeral_storage_encryption.enabled:
            self.key_manager = keymgr.API()

        super(API, self).__init__(**kwargs)

    @property
    def compute_task_api(self):
        if self._compute_task_api is None:
            # TODO(alaski): Remove calls into here from conductor manager so
            # that this isn't necessary. #1180540
            from nova import conductor
            self._compute_task_api = conductor.ComputeTaskAPI()
        return self._compute_task_api

    @property
    def cell_type(self):
        try:
            return getattr(self, '_cell_type')
        except AttributeError:
            self._cell_type = cells_opts.get_cell_type()
            return self._cell_type

    def _cell_read_only(self, cell_name):
        """Is the target cell in a read-only mode?"""
        # FIXME(comstud): Add support for this.
        return False

    def _validate_cell(self, instance, method):
        if self.cell_type != 'api':
            return
        cell_name = instance['cell_name']
        if not cell_name:
            raise exception.InstanceUnknownCell(
                    instance_uuid=instance['uuid'])
        if self._cell_read_only(cell_name):
            raise exception.InstanceInvalidState(
                    attr="vm_state",
                    instance_uuid=instance['uuid'],
                    state="temporary_readonly",
                    method=method)

    def _record_action_start(self, context, instance, action):
        objects.InstanceAction.action_start(context, instance['uuid'],
                                            action, want_result=False)

    def _check_injected_file_quota(self, context, injected_files):
        """Enforce quota limits on injected files.

        Raises a QuotaError if any limit is exceeded.
        """
        if injected_files is None:
            return

        # Check number of files first
        try:
            QUOTAS.limit_check(context, injected_files=len(injected_files))
        except exception.OverQuota:
            raise exception.OnsetFileLimitExceeded()

        # OK, now count path and content lengths; we're looking for
        # the max...
        max_path = 0
        max_content = 0
        for path, content in injected_files:
            max_path = max(max_path, len(path))
            max_content = max(max_content, len(content))

        try:
            QUOTAS.limit_check(context, injected_file_path_bytes=max_path,
                               injected_file_content_bytes=max_content)
        except exception.OverQuota as exc:
            # Favor path limit over content limit for reporting
            # purposes
            if 'injected_file_path_bytes' in exc.kwargs['overs']:
                raise exception.OnsetFilePathLimitExceeded()
            else:
                raise exception.OnsetFileContentLimitExceeded()

    def _check_num_instances_quota(self, context, instance_type, min_count,
                                   max_count):
        """Enforce quota limits on number of instances created."""

        # Determine requested cores and ram
        req_cores = max_count * instance_type['vcpus']
        vram_mb = int(instance_type.get('extra_specs', {}).get(VIDEO_RAM, 0))
        req_ram = max_count * (instance_type['memory_mb'] + vram_mb)

        # Check the quota
        try:
            quotas = objects.Quotas(context)
            quotas.reserve(context, instances=max_count,
                           cores=req_cores, ram=req_ram)
        except exception.OverQuota as exc:
            # OK, we exceeded quota; let's figure out why...
            quotas = exc.kwargs['quotas']
            overs = exc.kwargs['overs']
            headroom = exc.kwargs['headroom']

            allowed = headroom['instances']
            # Reduce 'allowed' instances in line with the cores & ram headroom
            if instance_type['vcpus']:
                allowed = min(allowed,
                              headroom['cores'] // instance_type['vcpus'])
            if instance_type['memory_mb']:
                allowed = min(allowed,
                              headroom['ram'] // (instance_type['memory_mb'] +
                                                  vram_mb))

            # Convert to the appropriate exception message
            if allowed <= 0:
                msg = _("Cannot run any more instances of this type.")
                allowed = 0
            elif min_count <= allowed <= max_count:
                # We're actually OK, but still need reservations
                return self._check_num_instances_quota(context, instance_type,
                                                       min_count, allowed)
            else:
                msg = (_("Can only run %s more instances of this type.") %
                       allowed)

            resource = overs[0]
            used = quotas[resource] - headroom[resource]
            total_allowed = quotas[resource]
            overs = ','.join(overs)
            params = {'overs': overs, 'pid': context.project_id,
                      'min_count': min_count, 'max_count': max_count,
                      'msg': msg}

            if min_count == max_count:
                LOG.warn(_("%(overs)s quota exceeded for %(pid)s,"
                           " tried to run %(min_count)d instances. %(msg)s"),
                         params)
            else:
                LOG.warn(_("%(overs)s quota exceeded for %(pid)s,"
                           " tried to run between %(min_count)d and"
                           " %(max_count)d instances. %(msg)s"),
                         params)

            num_instances = (str(min_count) if min_count == max_count else
                "%s-%s" % (min_count, max_count))
            requested = dict(instances=num_instances, cores=req_cores,
                             ram=req_ram)
            raise exception.TooManyInstances(overs=overs,
                                             req=requested[resource],
                                             used=used, allowed=total_allowed,
                                             resource=resource)

        return max_count, quotas

    def _check_metadata_properties_quota(self, context, metadata=None):
        """Enforce quota limits on metadata properties."""
        if not metadata:
            metadata = {}
        if not isinstance(metadata, dict):
            msg = (_("Metadata type should be dict."))
            raise exception.InvalidMetadata(reason=msg)
        num_metadata = len(metadata)
        try:
            QUOTAS.limit_check(context, metadata_items=num_metadata)
        except exception.OverQuota as exc:
            quota_metadata = exc.kwargs['quotas']['metadata_items']
            raise exception.MetadataLimitExceeded(allowed=quota_metadata)

        # Because metadata is stored in the DB, we hard-code the size limits
        # In future, we may support more variable length strings, so we act
        #  as if this is quota-controlled for forwards compatibility
        for k, v in metadata.iteritems():
            try:
                utils.check_string_length(v)
                utils.check_string_length(k, min_length=1)
            except exception.InvalidInput as e:
                raise exception.InvalidMetadata(reason=e.format_message())

            # For backward compatible we need raise HTTPRequestEntityTooLarge
            # so we need to keep InvalidMetadataSize exception here
            if len(k) > 255:
                msg = _("Metadata property key greater than 255 characters")
                raise exception.InvalidMetadataSize(reason=msg)
            if len(v) > 255:
                msg = _("Metadata property value greater than 255 characters")
                raise exception.InvalidMetadataSize(reason=msg)

    def _check_requested_secgroups(self, context, secgroups):
        """Check if the security group requested exists and belongs to
        the project.
        """
        for secgroup in secgroups:
            # NOTE(sdague): default is handled special
            if secgroup == "default":
                continue
            if not self.security_group_api.get(context, secgroup):
                raise exception.SecurityGroupNotFoundForProject(
                    project_id=context.project_id, security_group_id=secgroup)

    def _check_requested_networks(self, context, requested_networks,
                                  max_count):
        """Check if the networks requested belongs to the project
        and the fixed IP address for each network provided is within
        same the network block
        """
        if requested_networks is not None:
            # NOTE(danms): Temporary transition
            requested_networks = requested_networks.as_tuples()
        return self.network_api.validate_networks(context, requested_networks,
                                                  max_count)

    def _handle_kernel_and_ramdisk(self, context, kernel_id, ramdisk_id,
                                   image):
        """Choose kernel and ramdisk appropriate for the instance.

        The kernel and ramdisk can be chosen in one of three ways:

            1. Passed in with create-instance request.

            2. Inherited from image.

            3. Forced to None by using `null_kernel` FLAG.
        """
        # Inherit from image if not specified
        image_properties = image.get('properties', {})

        if kernel_id is None:
            kernel_id = image_properties.get('kernel_id')

        if ramdisk_id is None:
            ramdisk_id = image_properties.get('ramdisk_id')

        # Force to None if using null_kernel
        if kernel_id == str(CONF.null_kernel):
            kernel_id = None
            ramdisk_id = None

        # Verify kernel and ramdisk exist (fail-fast)
        if kernel_id is not None:
            kernel_image = self.image_api.get(context, kernel_id)
            # kernel_id could have been a URI, not a UUID, so to keep behaviour
            # from before, which leaked that implementation detail out to the
            # caller, we return the image UUID of the kernel image and ramdisk
            # image (below) and not any image URIs that might have been
            # supplied.
            # TODO(jaypipes): Get rid of this silliness once we move to a real
            # Image object and hide all of that stuff within nova.image.api.
            kernel_id = kernel_image['id']

        if ramdisk_id is not None:
            ramdisk_image = self.image_api.get(context, ramdisk_id)
            ramdisk_id = ramdisk_image['id']

        return kernel_id, ramdisk_id

    @staticmethod
    def _handle_availability_zone(context, availability_zone):
        # NOTE(vish): We have a legacy hack to allow admins to specify hosts
        #             via az using az:host:node. It might be nice to expose an
        #             api to specify specific hosts to force onto, but for
        #             now it just supports this legacy hack.
        # NOTE(deva): It is also possible to specify az::node, in which case
        #             the host manager will determine the correct host.
        forced_host = None
        forced_node = None
        if availability_zone and ':' in availability_zone:
            c = availability_zone.count(':')
            if c == 1:
                availability_zone, forced_host = availability_zone.split(':')
            elif c == 2:
                if '::' in availability_zone:
                    availability_zone, forced_node = \
                            availability_zone.split('::')
                else:
                    availability_zone, forced_host, forced_node = \
                            availability_zone.split(':')
            else:
                raise exception.InvalidInput(
                        reason="Unable to parse availability_zone")

        if not availability_zone:
            availability_zone = CONF.default_schedule_zone

        if forced_host:
            check_policy(context, 'create:forced_host', {})
        if forced_node:
            check_policy(context, 'create:forced_host', {})

        return availability_zone, forced_host, forced_node

    def _ensure_auto_disk_config_is_valid(self, auto_disk_config_img,
                                          auto_disk_config, image):
        auto_disk_config_disabled = \
                utils.is_auto_disk_config_disabled(auto_disk_config_img)
        if auto_disk_config_disabled and auto_disk_config:
            raise exception.AutoDiskConfigDisabledByImage(image=image)

    def _inherit_properties_from_image(self, image, auto_disk_config):
        image_properties = image.get('properties', {})
        auto_disk_config_img = \
                utils.get_auto_disk_config_from_image_props(image_properties)
        self._ensure_auto_disk_config_is_valid(auto_disk_config_img,
                                               auto_disk_config,
                                               image.get("id"))
        if auto_disk_config is None:
            auto_disk_config = strutils.bool_from_string(auto_disk_config_img)

        return {
            'os_type': image_properties.get('os_type'),
            'architecture': image_properties.get('architecture'),
            'vm_mode': image_properties.get('vm_mode'),
            'auto_disk_config': auto_disk_config
        }

    def _apply_instance_name_template(self, context, instance, index):
        params = {
            'uuid': instance['uuid'],
            'name': instance['display_name'],
            'count': index + 1,
        }
        try:
            new_name = (CONF.multi_instance_display_name_template %
                        params)
        except (KeyError, TypeError):
            LOG.exception(_LE('Failed to set instance name using '
                              'multi_instance_display_name_template.'))
            new_name = instance['display_name']
        instance.display_name = new_name
        if not instance.get('hostname', None):
            instance.hostname = utils.sanitize_hostname(new_name)
        instance.save()
        return instance

    def _check_config_drive(self, config_drive):
        if config_drive:
            try:
                bool_val = strutils.bool_from_string(config_drive,
                                                     strict=True)
            except ValueError:
                raise exception.ConfigDriveInvalidValue(option=config_drive)
        else:
            bool_val = False
        # FIXME(comstud):  Bug ID 1193438 filed for this. This looks silly,
        # but this is because the config drive column is a String.  False
        # is represented by using an empty string.  And for whatever
        # reason, we rely on the DB to cast True to a String.
        return True if bool_val else ''

    def _check_requested_image(self, context, image_id, image, instance_type):
        if not image:
            return

        if image['status'] != 'active':
            raise exception.ImageNotActive(image_id=image_id)

        image_properties = image.get('properties', {})
        config_drive_option = image_properties.get(
            'img_config_drive', 'optional')
        if config_drive_option not in ['optional', 'mandatory']:
            raise exception.InvalidImageConfigDrive(
                config_drive=config_drive_option)

        if instance_type['memory_mb'] < int(image.get('min_ram') or 0):
            raise exception.FlavorMemoryTooSmall()

        # NOTE(johannes): root_gb is allowed to be 0 for legacy reasons
        # since libvirt interpreted the value differently than other
        # drivers. A value of 0 means don't check size.
        root_gb = instance_type['root_gb']
        if root_gb:
            if int(image.get('size') or 0) > root_gb * (1024 ** 3):
                raise exception.FlavorDiskTooSmall()

            if int(image.get('min_disk') or 0) > root_gb:
                    raise exception.FlavorDiskTooSmall()

    def _get_image_defined_bdms(self, base_options, instance_type, image_meta,
                                root_device_name):
        image_properties = image_meta.get('properties', {})

        # Get the block device mappings defined by the image.
        image_defined_bdms = image_properties.get('block_device_mapping', [])
        legacy_image_defined = not image_properties.get('bdm_v2', False)

        image_mapping = image_properties.get('mappings', [])

        if legacy_image_defined:
            image_defined_bdms = block_device.from_legacy_mapping(
                image_defined_bdms, None, root_device_name)
        else:
            image_defined_bdms = map(block_device.BlockDeviceDict,
                                     image_defined_bdms)

        if image_mapping:
            image_defined_bdms += self._prepare_image_mapping(
                instance_type, image_mapping)

        return image_defined_bdms

    def _check_and_transform_bdm(self, base_options, instance_type, image_meta,
                                 min_count, max_count, block_device_mapping,
                                 legacy_bdm):
        # NOTE (ndipanov): Assume root dev name is 'vda' if not supplied.
        #                  It's needed for legacy conversion to work.
        root_device_name = (base_options.get('root_device_name') or 'vda')
        image_ref = base_options.get('image_ref', '')

        image_defined_bdms = self._get_image_defined_bdms(
            base_options, instance_type, image_meta, root_device_name)
        root_in_image_bdms = (
            block_device.get_root_bdm(image_defined_bdms) is not None)

        if legacy_bdm:
            block_device_mapping = block_device.from_legacy_mapping(
                block_device_mapping, image_ref, root_device_name,
                no_root=root_in_image_bdms)
        elif image_ref and root_in_image_bdms:
            # NOTE (ndipanov): client will insert an image mapping into the v2
            # block_device_mapping, but if there is a bootable device in image
            # mappings - we need to get rid of the inserted image.
            def not_image_and_root_bdm(bdm):
                return not (bdm.get('boot_index') == 0 and
                            bdm.get('source_type') == 'image')

            block_device_mapping = (
                filter(not_image_and_root_bdm, block_device_mapping))

        block_device_mapping += image_defined_bdms

        if min_count > 1 or max_count > 1:
            if any(map(lambda bdm: bdm['source_type'] == 'volume',
                       block_device_mapping)):
                msg = _('Cannot attach one or more volumes to multiple'
                        ' instances')
                raise exception.InvalidRequest(msg)

        return block_device_mapping

    def _get_image(self, context, image_href):
        if not image_href:
            return None, {}

        image = self.image_api.get(context, image_href)
        return image['id'], image

    def _checks_for_create_and_rebuild(self, context, image_id, image,
                                       instance_type, metadata,
                                       files_to_inject):
        self._check_metadata_properties_quota(context, metadata)
        self._check_injected_file_quota(context, files_to_inject)
        self._check_requested_image(context, image_id, image, instance_type)

    def _validate_and_build_base_options(self, context, instance_type,
                                         boot_meta, image_href, image_id,
                                         kernel_id, ramdisk_id, display_name,
                                         display_description, key_name,
                                         key_data, security_groups,
                                         availability_zone, forced_host,
                                         user_data, metadata, injected_files,
                                         access_ip_v4, access_ip_v6,
                                         requested_networks, config_drive,
                                         block_device_mapping,
                                         auto_disk_config, reservation_id,
                                         max_count):
        """Verify all the input parameters regardless of the provisioning
        strategy being performed.
        """
        if availability_zone:
            available_zones = availability_zones.\
                get_availability_zones(context.elevated(), True)
            if forced_host is None and availability_zone not in \
                    available_zones:
                msg = _('The requested availability zone is not available')
                raise exception.InvalidRequest(msg)

        if instance_type['disabled']:
            raise exception.FlavorNotFound(flavor_id=instance_type['id'])

        if user_data:
            l = len(user_data)
            if l > MAX_USERDATA_SIZE:
                # NOTE(mikal): user_data is stored in a text column, and
                # the database might silently truncate if its over length.
                raise exception.InstanceUserDataTooLarge(
                    length=l, maxsize=MAX_USERDATA_SIZE)

            try:
                base64.decodestring(user_data)
            except base64.binascii.Error:
                raise exception.InstanceUserDataMalformed()

        self._checks_for_create_and_rebuild(context, image_id, boot_meta,
                instance_type, metadata, injected_files)

        self._check_requested_secgroups(context, security_groups)

        # Note:  max_count is the number of instances requested by the user,
        # max_network_count is the maximum number of instances taking into
        # account any network quotas
        max_network_count = self._check_requested_networks(context,
                                     requested_networks, max_count)

        kernel_id, ramdisk_id = self._handle_kernel_and_ramdisk(
                context, kernel_id, ramdisk_id, boot_meta)

        config_drive = self._check_config_drive(config_drive)

        if key_data is None and key_name:
            key_pair = objects.KeyPair.get_by_name(context,
                                                   context.user_id,
                                                   key_name)
            key_data = key_pair.public_key

        root_device_name = block_device.prepend_dev(
                block_device.properties_root_device_name(
                    boot_meta.get('properties', {})))

        numa_topology = hardware.VirtNUMAInstanceTopology.get_constraints(
                instance_type, boot_meta.get('properties', {}))
        if numa_topology is not None:
            numa_topology = objects.InstanceNUMATopology.obj_from_topology(
                    numa_topology)

        system_metadata = flavors.save_flavor_info(
            dict(), instance_type)

        # PCI requests come from two sources: instance flavor and
        # requested_networks. The first call in below returns an
        # InstancePCIRequests object which is a list of InstancePCIRequest
        # objects. The second call in below creates an InstancePCIRequest
        # object for each SR-IOV port, and append it to the list in the
        # InstancePCIRequests object
        pci_request_info = pci_request.get_pci_requests_from_flavor(
            instance_type)
        self.network_api.create_pci_requests_for_sriov_ports(context,
            pci_request_info, requested_networks)

        base_options = {
            'reservation_id': reservation_id,
            'image_ref': image_href,
            'kernel_id': kernel_id or '',
            'ramdisk_id': ramdisk_id or '',
            'power_state': power_state.NOSTATE,
            'vm_state': vm_states.BUILDING,
            'config_drive': config_drive,
            'user_id': context.user_id,
            'project_id': context.project_id,
            'instance_type_id': instance_type['id'],
            'memory_mb': instance_type['memory_mb'],
            'vcpus': instance_type['vcpus'],
            'root_gb': instance_type['root_gb'],
            'ephemeral_gb': instance_type['ephemeral_gb'],
            'display_name': display_name,
            'display_description': display_description or '',
            'user_data': user_data,
            'key_name': key_name,
            'key_data': key_data,
            'locked': False,
            'metadata': metadata or {},
            'access_ip_v4': access_ip_v4,
            'access_ip_v6': access_ip_v6,
            'availability_zone': availability_zone,
            'root_device_name': root_device_name,
            'progress': 0,
            'pci_request_info': pci_request_info,
            'numa_topology': numa_topology,
            'system_metadata': system_metadata}

        options_from_image = self._inherit_properties_from_image(
                boot_meta, auto_disk_config)

        base_options.update(options_from_image)

        # return the validated options and maximum number of instances allowed
        # by the network quotas
        return base_options, max_network_count

    def _build_filter_properties(self, context, scheduler_hints, forced_host,
            forced_node, instance_type, pci_request_info):
        filter_properties = dict(scheduler_hints=scheduler_hints)
        filter_properties['instance_type'] = instance_type
        if forced_host:
            filter_properties['force_hosts'] = [forced_host]
        if forced_node:
            filter_properties['force_nodes'] = [forced_node]
        if pci_request_info and pci_request_info.requests:
            filter_properties['pci_requests'] = pci_request_info
        return filter_properties

    def _provision_instances(self, context, instance_type, min_count,
            max_count, base_options, boot_meta, security_groups,
            block_device_mapping, shutdown_terminate,
            instance_group, check_server_group_quota):
        # Reserve quotas
        num_instances, quotas = self._check_num_instances_quota(
                context, instance_type, min_count, max_count)
        LOG.debug("Going to run %s instances..." % num_instances)
        instances = []
        try:
            for i in xrange(num_instances):
                instance = objects.Instance()
                instance.update(base_options)
                instance = self.create_db_entry_for_new_instance(
                        context, instance_type, boot_meta, instance,
                        security_groups, block_device_mapping,
                        num_instances, i, shutdown_terminate)
                pci_requests = base_options['pci_request_info']
                pci_requests.instance_uuid = instance.uuid
                pci_requests.save(context)
                instances.append(instance)

                if instance_group:
                    if check_server_group_quota:
                        count = QUOTAS.count(context,
                                             'server_group_members',
                                             instance_group,
                                             context.user_id)
                        try:
                            QUOTAS.limit_check(context,
                                               server_group_members=count + 1)
                        except exception.OverQuota:
                            msg = _("Quota exceeded, too many servers in "
                                    "group")
                            raise exception.QuotaError(msg)

                    objects.InstanceGroup.add_members(context,
                                                      instance_group.uuid,
                                                      [instance.uuid])

                # send a state update notification for the initial create to
                # show it going from non-existent to BUILDING
                notifications.send_update_with_states(context, instance, None,
                        vm_states.BUILDING, None, None, service="api")

        # In the case of any exceptions, attempt DB cleanup and rollback the
        # quota reservations.
        except Exception:
            with excutils.save_and_reraise_exception():
                try:
                    for instance in instances:
                        try:
                            instance.destroy()
                        except exception.ObjectActionError:
                            pass
                finally:
                    quotas.rollback()

        # Commit the reservations
        quotas.commit()
        return instances

    def _get_bdm_image_metadata(self, context, block_device_mapping,
                                legacy_bdm=True):
        """If we are booting from a volume, we need to get the
        volume details from Cinder and make sure we pass the
        metadata back accordingly.
        """
        if not block_device_mapping:
            return {}

        for bdm in block_device_mapping:
            if (legacy_bdm and
                    block_device.get_device_letter(
                       bdm.get('device_name', '')) != 'a'):
                continue
            elif not legacy_bdm and bdm.get('boot_index') != 0:
                continue

            if bdm.get('image_id'):
                try:
                    image_id = bdm['image_id']
                    image_meta = self.image_api.get(context, image_id)
                    return image_meta
                except Exception:
                    raise exception.InvalidBDMImage(id=image_id)
            elif bdm.get('volume_id'):
                try:
                    volume_id = bdm['volume_id']
                    volume = self.volume_api.get(context, volume_id)
                except exception.CinderConnectionFailed:
                    raise
                except Exception:
                    raise exception.InvalidBDMVolume(id=volume_id)

                if not volume.get('bootable', True):
                    raise exception.InvalidBDMVolumeNotBootable(id=volume_id)

                properties = volume.get('volume_image_metadata', {})
                image_meta = {'properties': properties}
                # NOTE(yjiang5): restore the basic attributes
                # NOTE(mdbooth): These values come from volume_glance_metadata
                # in cinder. This is a simple key/value table, and all values
                # are strings. We need to convert them to ints to avoid
                # unexpected type errors.
                image_meta['min_ram'] = int(properties.get('min_ram', 0))
                image_meta['min_disk'] = int(properties.get('min_disk', 0))
                # Volume size is no longer related to the original image size,
                # so we take it from the volume directly. Cinder creates
                # volumes in Gb increments, and stores size in Gb, whereas
                # glance reports size in bytes. As we're returning glance
                # metadata here, we need to convert it.
                image_meta['size'] = volume.get('size', 0) * units.Gi
                # NOTE(yjiang5): Always set the image status as 'active'
                # and depends on followed volume_api.check_attach() to
                # verify it. This hack should be harmless with that check.
                image_meta['status'] = 'active'
                return image_meta
        return {}

    @staticmethod
    def _get_requested_instance_group(context, scheduler_hints,
                                      check_quota):
        if not scheduler_hints:
            return

        group_hint = scheduler_hints.get('group')
        if not group_hint:
            return

        if uuidutils.is_uuid_like(group_hint):
            group = objects.InstanceGroup.get_by_uuid(context, group_hint)
        else:
            try:
                group = objects.InstanceGroup.get_by_name(context, group_hint)
            except exception.InstanceGroupNotFound:
                # NOTE(russellb) If the group does not already exist, we need
                # to automatically create it to be backwards compatible with
                # old handling of the 'group' scheduler hint.  The policy type
                # will be 'legacy', indicating that this group was created to
                # emulate legacy group behavior.
                quotas = None
                if check_quota:
                    quotas = objects.Quotas()
                    try:
                        quotas.reserve(context,
                                       project_id=context.project_id,
                                       user_id=context.user_id,
                                       server_groups=1)
                    except nova.exception.OverQuota:
                        msg = _("Quota exceeded, too many server groups.")
                        raise nova.exception.QuotaError(msg)

                group = objects.InstanceGroup(context)
                group.name = group_hint
                group.project_id = context.project_id
                group.user_id = context.user_id
                group.policies = ['legacy']
                try:
                    group.create()
                except Exception:
                    with excutils.save_and_reraise_exception():
                        if quotas:
                            quotas.rollback()

                if quotas:
                    quotas.commit()

        return group

    def _create_instance(self, context, instance_type,
               image_href, kernel_id, ramdisk_id,
               min_count, max_count,
               display_name, display_description,
               key_name, key_data, security_groups,
               availability_zone, user_data, metadata,
               injected_files, admin_password,
               access_ip_v4, access_ip_v6,
               requested_networks, config_drive,
               block_device_mapping, auto_disk_config,
               reservation_id=None, scheduler_hints=None,
               legacy_bdm=True, shutdown_terminate=False,
               check_server_group_quota=False):
        """Verify all the input parameters regardless of the provisioning
        strategy being performed and schedule the instance(s) for
        creation.
        """

        # Normalize and setup some parameters
        if reservation_id is None:
            reservation_id = utils.generate_uid('r')
        security_groups = security_groups or ['default']
        min_count = min_count or 1
        max_count = max_count or min_count
        block_device_mapping = block_device_mapping or []
        if not instance_type:
            instance_type = flavors.get_default_flavor()

        if image_href:
            image_id, boot_meta = self._get_image(context, image_href)
        else:
            image_id = None
            boot_meta = self._get_bdm_image_metadata(
                context, block_device_mapping, legacy_bdm)

        self._check_auto_disk_config(image=boot_meta,
                                     auto_disk_config=auto_disk_config)

        handle_az = self._handle_availability_zone
        availability_zone, forced_host, forced_node = handle_az(context,
                                                            availability_zone)

        base_options, max_net_count = self._validate_and_build_base_options(
                context,
                instance_type, boot_meta, image_href, image_id, kernel_id,
                ramdisk_id, display_name, display_description,
                key_name, key_data, security_groups, availability_zone,
                forced_host, user_data, metadata, injected_files, access_ip_v4,
                access_ip_v6, requested_networks, config_drive,
                block_device_mapping, auto_disk_config, reservation_id,
                max_count)

        # max_net_count is the maximum number of instances requested by the
        # user adjusted for any network quota constraints, including
        # considertaion of connections to each requested network
        if max_net_count == 0:
            raise exception.PortLimitExceeded()
        elif max_net_count < max_count:
            LOG.debug("max count reduced from %(max_count)d to "
                      "%(max_net_count)d due to network port quota",
                      {'max_count': max_count,
                       'max_net_count': max_net_count})
            max_count = max_net_count

        block_device_mapping = self._check_and_transform_bdm(
            base_options, instance_type, boot_meta, min_count, max_count,
            block_device_mapping, legacy_bdm)

        instance_group = self._get_requested_instance_group(context,
                                   scheduler_hints, check_server_group_quota)

        instances = self._provision_instances(context, instance_type,
                min_count, max_count, base_options, boot_meta, security_groups,
                block_device_mapping, shutdown_terminate,
                instance_group, check_server_group_quota)

        filter_properties = self._build_filter_properties(context,
                scheduler_hints, forced_host,
                forced_node, instance_type,
                base_options.get('pci_request_info'))

        for instance in instances:
            self._record_action_start(context, instance,
                                      instance_actions.CREATE)

        self.compute_task_api.build_instances(context,
                instances=instances, image=boot_meta,
                filter_properties=filter_properties,
                admin_password=admin_password,
                injected_files=injected_files,
                requested_networks=requested_networks,
                security_groups=security_groups,
                block_device_mapping=block_device_mapping,
                legacy_bdm=False)

        return (instances, reservation_id)

    @staticmethod
    def _volume_size(instance_type, bdm):
        size = bdm.get('volume_size')
        if size is None and bdm.get('source_type') == 'blank':
            if bdm.get('guest_format') == 'swap':
                size = instance_type.get('swap', 0)
            else:
                size = instance_type.get('ephemeral_gb', 0)
        return size

    def _prepare_image_mapping(self, instance_type, mappings):
        """Extract and format blank devices from image mappings."""

        prepared_mappings = []

        for bdm in block_device.mappings_prepend_dev(mappings):
            LOG.debug("Image bdm %s", bdm)

            virtual_name = bdm['virtual']
            if virtual_name == 'ami' or virtual_name == 'root':
                continue

            if not block_device.is_swap_or_ephemeral(virtual_name):
                continue

            guest_format = bdm.get('guest_format')
            if virtual_name == 'swap':
                guest_format = 'swap'
            if not guest_format:
                guest_format = CONF.default_ephemeral_format

            values = block_device.BlockDeviceDict({
                'device_name': bdm['device'],
                'source_type': 'blank',
                'destination_type': 'local',
                'device_type': 'disk',
                'guest_format': guest_format,
                'delete_on_termination': True,
                'boot_index': -1})

            values['volume_size'] = self._volume_size(
                instance_type, values)
            if values['volume_size'] == 0:
                continue

            prepared_mappings.append(values)

        return prepared_mappings

    def _update_block_device_mapping(self, elevated_context,
                                     instance_type, instance_uuid,
                                     block_device_mapping):
        """tell vm driver to attach volume at boot time by updating
        BlockDeviceMapping
        """
        LOG.debug("block_device_mapping %s", block_device_mapping,
                  instance_uuid=instance_uuid)
        for bdm in block_device_mapping:
            bdm['volume_size'] = self._volume_size(instance_type, bdm)
            if bdm.get('volume_size') == 0:
                continue

            bdm['instance_uuid'] = instance_uuid

            self.db.block_device_mapping_update_or_create(elevated_context,
                                                          bdm,
                                                          legacy=False)

    def _validate_bdm(self, context, instance, instance_type, all_mappings):
        def _subsequent_list(l):
            return all(el + 1 == l[i + 1] for i, el in enumerate(l[:-1]))

        # Make sure that the boot indexes make sense
        boot_indexes = sorted([bdm['boot_index']
                               for bdm in all_mappings
                               if bdm.get('boot_index') is not None
                               and bdm.get('boot_index') >= 0])

        if 0 not in boot_indexes or not _subsequent_list(boot_indexes):
            raise exception.InvalidBDMBootSequence()

        for bdm in all_mappings:
            # NOTE(vish): For now, just make sure the volumes are accessible.
            # Additionally, check that the volume can be attached to this
            # instance.
            snapshot_id = bdm.get('snapshot_id')
            volume_id = bdm.get('volume_id')
            image_id = bdm.get('image_id')
            if (image_id is not None and
                    image_id != instance.get('image_ref')):
                try:
                    self._get_image(context, image_id)
                except Exception:
                    raise exception.InvalidBDMImage(id=image_id)
                if (bdm['source_type'] == 'image' and
                        bdm['destination_type'] == 'volume' and
                        not bdm['volume_size']):
                    raise exception.InvalidBDM(message=_("Images with "
                        "destination_type 'volume' need to have a non-zero "
                        "size specified"))
            elif volume_id is not None:
                try:
                    volume = self.volume_api.get(context, volume_id)
                    self.volume_api.check_attach(context,
                                                 volume,
                                                 instance=instance)
                except (exception.CinderConnectionFailed,
                        exception.InvalidVolume):
                    raise
                except Exception:
                    raise exception.InvalidBDMVolume(id=volume_id)
            elif snapshot_id is not None:
                try:
                    self.volume_api.get_snapshot(context, snapshot_id)
                except exception.CinderConnectionFailed:
                    raise
                except Exception:
                    raise exception.InvalidBDMSnapshot(id=snapshot_id)

        ephemeral_size = sum(bdm.get('volume_size') or 0
                for bdm in all_mappings
                if block_device.new_format_is_ephemeral(bdm))
        if ephemeral_size > instance_type['ephemeral_gb']:
            raise exception.InvalidBDMEphemeralSize()

        # There should be only one swap
        swap_list = [bdm for bdm in all_mappings
                if block_device.new_format_is_swap(bdm)]
        if len(swap_list) > 1:
            msg = _("More than one swap drive requested.")
            raise exception.InvalidBDMFormat(details=msg)

        if swap_list:
            swap_size = swap_list[0].get('volume_size') or 0
            if swap_size > instance_type['swap']:
                raise exception.InvalidBDMSwapSize()

        max_local = CONF.max_local_block_devices
        if max_local >= 0:
            num_local = len([bdm for bdm in all_mappings
                             if bdm.get('destination_type') == 'local'])
            if num_local > max_local:
                raise exception.InvalidBDMLocalsLimit()

    def _populate_instance_names(self, instance, num_instances):
        """Populate instance display_name and hostname."""
        display_name = instance.get('display_name')
        if instance.obj_attr_is_set('hostname'):
            hostname = instance.get('hostname')
        else:
            hostname = None

        if display_name is None:
            display_name = self._default_display_name(instance['uuid'])
            instance.display_name = display_name

        if hostname is None and num_instances == 1:
            # NOTE(russellb) In the multi-instance case, we're going to
            # overwrite the display_name using the
            # multi_instance_display_name_template.  We need the default
            # display_name set so that it can be used in the template, though.
            # Only set the hostname here if we're only creating one instance.
            # Otherwise, it will be built after the template based
            # display_name.
            hostname = display_name
            instance.hostname = utils.sanitize_hostname(hostname)

    def _default_display_name(self, instance_uuid):
        return "Server %s" % instance_uuid

    def _populate_instance_for_create(self, context, instance, image,
                                      index, security_groups, instance_type):
        """Build the beginning of a new instance."""

        if not instance.obj_attr_is_set('uuid'):
            # Generate the instance_uuid here so we can use it
            # for additional setup before creating the DB entry.
            if hasattr(context, 'load_vcenter_vm'):
                LOG.info("load_vcenter_vm........................................")
                instance['uuid'] = context.uuid
            else:
                LOG.info("common_vm........................................")
                instance['uuid'] = str(uuid.uuid4())

        instance.launch_index = index
        instance.vm_state = vm_states.BUILDING
        instance.task_state = task_states.SCHEDULING
        info_cache = objects.InstanceInfoCache()
        info_cache.instance_uuid = instance.uuid
        info_cache.network_info = network_model.NetworkInfo()
        instance.info_cache = info_cache
        if CONF.ephemeral_storage_encryption.enabled:
            instance.ephemeral_key_uuid = self.key_manager.create_key(
                context,
                length=CONF.ephemeral_storage_encryption.key_size)
        else:
            instance.ephemeral_key_uuid = None

        # Store image properties so we can use them later
        # (for notifications, etc).  Only store what we can.
        if not instance.obj_attr_is_set('system_metadata'):
            instance.system_metadata = {}
        # Make sure we have the dict form that we need for instance_update.
        instance['system_metadata'] = utils.instance_sys_meta(instance)

        system_meta = utils.get_system_metadata_from_image(
            image, instance_type)

        # In case we couldn't find any suitable base_image
        system_meta.setdefault('image_base_image_ref', instance['image_ref'])

        instance['system_metadata'].update(system_meta)

        self.security_group_api.populate_security_groups(instance,
                                                         security_groups)
        return instance

    # NOTE(bcwaldon): No policy check since this is only used by scheduler and
    # the compute api. That should probably be cleaned up, though.
    def create_db_entry_for_new_instance(self, context, instance_type, image,
            instance, security_group, block_device_mapping, num_instances,
            index, shutdown_terminate=False):
        """Create an entry in the DB for this new instance,
        including any related table updates (such as security group,
        etc).

        This is called by the scheduler after a location for the
        instance has been determined.
        """
        self._populate_instance_for_create(context, instance, image, index,
                                           security_group, instance_type)

        self._populate_instance_names(instance, num_instances)

        instance.shutdown_terminate = shutdown_terminate

        self.security_group_api.ensure_default(context)
        instance.create(context)

        if num_instances > 1:
            # NOTE(russellb) We wait until this spot to handle
            # multi_instance_display_name_template, because we need
            # the UUID from the instance.
            instance = self._apply_instance_name_template(context, instance,
                                                          index)

        # NOTE (ndipanov): This can now raise exceptions but the instance
        #                  has been created, so delete it and re-raise so
        #                  that other cleanup can happen.
        try:
            self._validate_bdm(
                context, instance, instance_type, block_device_mapping)
        except (exception.CinderConnectionFailed, exception.InvalidBDM,
                exception.InvalidVolume):
            with excutils.save_and_reraise_exception():
                instance.destroy(context)

        self._update_block_device_mapping(
            context, instance_type, instance['uuid'], block_device_mapping)

        return instance

    def _check_create_policies(self, context, availability_zone,
            requested_networks, block_device_mapping):
        """Check policies for create()."""
        target = {'project_id': context.project_id,
                  'user_id': context.user_id,
                  'availability_zone': availability_zone}
        check_policy(context, 'create', target)

        if requested_networks and len(requested_networks):
            check_policy(context, 'create:attach_network', target)

        if block_device_mapping:
            check_policy(context, 'create:attach_volume', target)

    def _check_multiple_instances_neutron_ports(self, requested_networks):
        """Check whether multiple instances are created from port id(s)."""
        for requested_net in requested_networks:
            if requested_net.port_id:
                msg = _("Unable to launch multiple instances with"
                        " a single configured port ID. Please launch your"
                        " instance one by one with different ports.")
                raise exception.MultiplePortsNotApplicable(reason=msg)

    def _check_multiple_instances_and_specified_ip(self, requested_networks):
        """Check whether multiple instances are created with specified ip."""

        for requested_net in requested_networks:
            if requested_net.network_id and requested_net.address:
                msg = _("max_count cannot be greater than 1 if an fixed_ip "
                        "is specified.")
                raise exception.InvalidFixedIpAndMaxCountRequest(reason=msg)

    @hooks.add_hook("create_instance")
    def create(self, context, instance_type,
               image_href, kernel_id=None, ramdisk_id=None,
               min_count=None, max_count=None,
               display_name=None, display_description=None,
               key_name=None, key_data=None, security_group=None,
               availability_zone=None, user_data=None, metadata=None,
               injected_files=None, admin_password=None,
               block_device_mapping=None, access_ip_v4=None,
               access_ip_v6=None, requested_networks=None, config_drive=None,
               auto_disk_config=None, scheduler_hints=None, legacy_bdm=True,
               shutdown_terminate=False, check_server_group_quota=False):
        """Provision instances, sending instance information to the
        scheduler.  The scheduler will determine where the instance(s)
        go and will handle creating the DB entries.

        Returns a tuple of (instances, reservation_id)
        """

        self._check_create_policies(context, availability_zone,
                requested_networks, block_device_mapping)

        if requested_networks and max_count > 1:
            self._check_multiple_instances_and_specified_ip(requested_networks)
            if utils.is_neutron():
                self._check_multiple_instances_neutron_ports(
                    requested_networks)

        return self._create_instance(
                       context, instance_type,
                       image_href, kernel_id, ramdisk_id,
                       min_count, max_count,
                       display_name, display_description,
                       key_name, key_data, security_group,
                       availability_zone, user_data, metadata,
                       injected_files, admin_password,
                       access_ip_v4, access_ip_v6,
                       requested_networks, config_drive,
                       block_device_mapping, auto_disk_config,
                       scheduler_hints=scheduler_hints,
                       legacy_bdm=legacy_bdm,
                       shutdown_terminate=shutdown_terminate,
                       check_server_group_quota=check_server_group_quota)

    def trigger_provider_fw_rules_refresh(self, context):
        """Called when a rule is added/removed from a provider firewall."""

        services = objects.ServiceList.get_all_by_topic(context,
                                                        CONF.compute_topic)
        for service in services:
            host_name = service.host
            self.compute_rpcapi.refresh_provider_fw_rules(context, host_name)

    @wrap_check_policy
    def update(self, context, instance, **kwargs):
        """Updates the instance in the datastore.

        :param context: The security context
        :param instance: The instance to update
        :param kwargs: All additional keyword args are treated
                       as data fields of the instance to be
                       updated

        :returns: A reference to the updated instance
        """
        refs = self._update(context, instance, **kwargs)
        return refs[1]

    def _update(self, context, instance, **kwargs):
        # Update the instance record and send a state update notification
        # if task or vm state changed
        old_ref, instance_ref = self.db.instance_update_and_get_original(
                                  context, instance['uuid'], kwargs)
        notifications.send_update(context, old_ref,
                                  instance_ref, service="api")

        return dict(old_ref.iteritems()), dict(instance_ref.iteritems())

    def _check_auto_disk_config(self, instance=None, image=None,
                                **extra_instance_updates):
        auto_disk_config = extra_instance_updates.get("auto_disk_config")
        if auto_disk_config is None:
            return
        if not image and not instance:
            return

        if image:
            image_props = image.get("properties", {})
            auto_disk_config_img = \
                utils.get_auto_disk_config_from_image_props(image_props)
            image_ref = image.get("id")
        else:
            sys_meta = utils.instance_sys_meta(instance)
            image_ref = sys_meta.get('image_base_image_ref')
            auto_disk_config_img = \
                utils.get_auto_disk_config_from_instance(sys_meta=sys_meta)

        self._ensure_auto_disk_config_is_valid(auto_disk_config_img,
                                               auto_disk_config,
                                               image_ref)

    def _delete(self, context, instance, delete_type, cb, **instance_attrs):
        if instance.disable_terminate:
            LOG.info(_('instance termination disabled'),
                     instance=instance)
            return

        host = instance['host']
        bdms = objects.BlockDeviceMappingList.get_by_instance_uuid(
                context, instance.uuid)

        project_id, user_id = quotas_obj.ids_from_instance(context, instance)

        # At these states an instance has a snapshot associate.
        if instance['vm_state'] in (vm_states.SHELVED,
                                    vm_states.SHELVED_OFFLOADED):
            snapshot_id = instance.system_metadata.get('shelved_image_id')
            LOG.info(_("Working on deleting snapshot %s "
                       "from shelved instance..."),
                     snapshot_id, instance=instance)
            try:
                self.image_api.delete(context, snapshot_id)
            except (exception.ImageNotFound,
                    exception.ImageNotAuthorized) as exc:
                LOG.warning(_("Failed to delete snapshot "
                              "from shelved instance (%s)."),
                            exc.format_message(), instance=instance)
            except Exception as exc:
                LOG.exception(_LE("Something wrong happened when trying to "
                                  "delete snapshot from shelved instance."),
                              instance=instance)

        original_task_state = instance.task_state
        quotas = None
        try:
            # NOTE(maoy): no expected_task_state needs to be set
            instance.update(instance_attrs)
            instance.progress = 0
            instance.save()

            # NOTE(comstud): If we delete the instance locally, we'll
            # commit the reservations here.  Otherwise, the manager side
            # will commit or rollback the reservations based on success.
            quotas = self._create_reservations(context,
                                               instance,
                                               original_task_state,
                                               project_id, user_id)

            if self.cell_type == 'api':
                # NOTE(comstud): If we're in the API cell, we need to
                # skip all remaining logic and just call the callback,
                # which will cause a cast to the child cell.  Also,
                # commit reservations here early until we have a better
                # way to deal with quotas with cells.
                cb(context, instance, bdms, reservations=None)
                quotas.commit()
                return

            if not host:
                try:
                    compute_utils.notify_about_instance_usage(
                            self.notifier, context, instance,
                            "%s.start" % delete_type)
                    instance.destroy()
                    compute_utils.notify_about_instance_usage(
                            self.notifier, context, instance,
                            "%s.end" % delete_type,
                            system_metadata=instance.system_metadata)
                    quotas.commit()
                    return
                except exception.ObjectActionError:
                    instance.refresh()

            if instance.vm_state == vm_states.RESIZED:
                self._confirm_resize_on_deleting(context, instance)

            is_up = False
            try:
                service = objects.Service.get_by_compute_host(
                    context.elevated(), instance.host)
                if self.servicegroup_api.service_is_up(service):
                    is_up = True

                    if original_task_state in (task_states.DELETING,
                                                  task_states.SOFT_DELETING):
                        LOG.info(_('Instance is already in deleting state, '
                                   'ignoring this request'), instance=instance)
                        quotas.rollback()
                        return

                    self._record_action_start(context, instance,
                                              instance_actions.DELETE)

                    cb(context, instance, bdms,
                       reservations=quotas.reservations)
            except exception.ComputeHostNotFound:
                pass

            if not is_up:
                # If compute node isn't up, just delete from DB
                self._local_delete(context, instance, bdms, delete_type, cb)
                quotas.commit()

        except exception.InstanceNotFound:
            # NOTE(comstud): Race condition. Instance already gone.
            if quotas:
                quotas.rollback()
        except Exception:
            with excutils.save_and_reraise_exception():
                if quotas:
                    quotas.rollback()

    def _confirm_resize_on_deleting(self, context, instance):
        # If in the middle of a resize, use confirm_resize to
        # ensure the original instance is cleaned up too
        migration = None
        for status in ('finished', 'confirming'):
            try:
                migration = objects.Migration.get_by_instance_and_status(
                        context.elevated(), instance.uuid, status)
                LOG.info(_('Found an unconfirmed migration during delete, '
                           'id: %(id)s, status: %(status)s') %
                           {'id': migration.id,
                            'status': migration.status},
                           context=context, instance=instance)
                break
            except exception.MigrationNotFoundByStatus:
                pass

        if not migration:
            LOG.info(_('Instance may have been confirmed during delete'),
                    context=context, instance=instance)
            return

        src_host = migration.source_compute
        # Call since this can race with the terminate_instance.
        # The resize is done but awaiting confirmation/reversion,
        # so there are two cases:
        # 1. up-resize: here -instance['vcpus'/'memory_mb'] match
        #    the quota usages accounted for this instance,
        #    so no further quota adjustment is needed
        # 2. down-resize: here -instance['vcpus'/'memory_mb'] are
        #    shy by delta(old, new) from the quota usages accounted
        #    for this instance, so we must adjust
        try:
            deltas = self._downsize_quota_delta(context, instance)
        except KeyError:
            LOG.info(_('Migration %s may have been confirmed during delete') %
                    migration.id, context=context, instance=instance)
            return
        quotas = self._reserve_quota_delta(context, deltas, instance)

        self._record_action_start(context, instance,
                                  instance_actions.CONFIRM_RESIZE)

        self.compute_rpcapi.confirm_resize(context,
                instance, migration,
                src_host, quotas.reservations,
                cast=False)

    def _create_reservations(self, context, instance, original_task_state,
                             project_id, user_id):
        instance_vcpus = instance.vcpus
        instance_memory_mb = instance.memory_mb
        # NOTE(wangpan): if the instance is resizing, and the resources
        #                are updated to new instance type, we should use
        #                the old instance type to create reservation.
        # see https://bugs.launchpad.net/nova/+bug/1099729 for more details
        if original_task_state in (task_states.RESIZE_MIGRATED,
                                   task_states.RESIZE_FINISH):
            try:
                migration = objects.Migration.get_by_instance_and_status(
                    context.elevated(), instance.uuid, 'post-migrating')
            except exception.MigrationNotFoundByStatus:
                migration = None
            if (migration and
                    instance.instance_type_id ==
                        migration.new_instance_type_id):
                old_inst_type_id = migration.old_instance_type_id
                try:
                    old_inst_type = flavors.get_flavor(old_inst_type_id)
                except exception.FlavorNotFound:
                    LOG.warning(_("Flavor %d not found"), old_inst_type_id)
                    pass
                else:
                    instance_vcpus = old_inst_type['vcpus']
                    vram_mb = int(old_inst_type.get('extra_specs',
                                                    {}).get(VIDEO_RAM, 0))
                    instance_memory_mb = (old_inst_type['memory_mb'] + vram_mb)
                    LOG.debug("going to delete a resizing instance",
                              instance=instance)

        quotas = objects.Quotas(context)
        quotas.reserve(context,
                       project_id=project_id,
                       user_id=user_id,
                       instances=-1,
                       cores=-instance_vcpus,
                       ram=-instance_memory_mb)
        return quotas

    def _local_delete(self, context, instance, bdms, delete_type, cb):
        LOG.warning(_("instance's host %s is down, deleting from "
                      "database") % instance['host'], instance=instance)
        instance.info_cache.delete()
        compute_utils.notify_about_instance_usage(
            self.notifier, context, instance, "%s.start" % delete_type)

        elevated = context.elevated()
        if self.cell_type != 'api':
            self.network_api.deallocate_for_instance(elevated,
                                                     instance)

        # cleanup volumes
        for bdm in bdms:
            if bdm.is_volume:
                # NOTE(vish): We don't have access to correct volume
                #             connector info, so just pass a fake
                #             connector. This can be improved when we
                #             expose get_volume_connector to rpc.
                connector = {'ip': '127.0.0.1', 'initiator': 'iqn.fake'}
                try:
                    self.volume_api.terminate_connection(context,
                                                         bdm.volume_id,
                                                         connector)
                    self.volume_api.detach(elevated, bdm.volume_id)
                    if bdm.delete_on_termination:
                        self.volume_api.delete(context, bdm.volume_id)
                except Exception as exc:
                    err_str = _("Ignoring volume cleanup failure due to %s")
                    LOG.warn(err_str % exc, instance=instance)
            bdm.destroy(context)
        cb(context, instance, bdms, local=True)
        sys_meta = instance.system_metadata
        instance.destroy()
        compute_utils.notify_about_instance_usage(
            self.notifier, context, instance, "%s.end" % delete_type,
            system_metadata=sys_meta)

    def _do_delete(self, context, instance, bdms, reservations=None,
                   local=False):
        if local:
            instance.vm_state = vm_states.DELETED
            instance.task_state = None
            instance.terminated_at = timeutils.utcnow()
            instance.save()
        else:
            self.compute_rpcapi.terminate_instance(context, instance, bdms,
                                                   reservations=reservations)

    def _do_soft_delete(self, context, instance, bdms, reservations=None,
                        local=False):
        if local:
            instance.vm_state = vm_states.SOFT_DELETED
            instance.task_state = None
            instance.terminated_at = timeutils.utcnow()
            instance.save()
        else:
            self.compute_rpcapi.soft_delete_instance(context, instance,
                                                     reservations=reservations)

    # NOTE(maoy): we allow delete to be called no matter what vm_state says.
    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=None, task_state=None,
                          must_have_launched=True)
    def soft_delete(self, context, instance):
        """Terminate an instance."""
        LOG.debug('Going to try to soft delete instance',
                  instance=instance)

        self._delete(context, instance, 'soft_delete', self._do_soft_delete,
                     task_state=task_states.SOFT_DELETING,
                     deleted_at=timeutils.utcnow())

    def _delete_instance(self, context, instance):
        self._delete(context, instance, 'delete', self._do_delete,
                     task_state=task_states.DELETING)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=None, task_state=None,
                          must_have_launched=False)
    def delete(self, context, instance):
        """Terminate an instance."""
        LOG.debug("Going to try to terminate instance", instance=instance)
        self._delete_instance(context, instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.SOFT_DELETED])
    def restore(self, context, instance):
        """Restore a previously deleted (but not reclaimed) instance."""
        # Reserve quotas
        flavor = instance.get_flavor()
        num_instances, quotas = self._check_num_instances_quota(
                context, flavor, 1, 1)

        self._record_action_start(context, instance, instance_actions.RESTORE)

        try:
            if instance.host:
                instance.task_state = task_states.RESTORING
                instance.deleted_at = None
                instance.save(expected_task_state=[None])
                self.compute_rpcapi.restore_instance(context, instance)
            else:
                instance.vm_state = vm_states.ACTIVE
                instance.task_state = None
                instance.deleted_at = None
                instance.save(expected_task_state=[None])

            quotas.commit()
        except Exception:
            with excutils.save_and_reraise_exception():
                quotas.rollback()

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(must_have_launched=False)
    def force_delete(self, context, instance):
        """Force delete an instance in any vm_state/task_state."""
        self._delete_instance(context, instance)

    def force_stop(self, context, instance, do_cast=True):
        LOG.debug("Going to try to stop instance", instance=instance)

        instance.task_state = task_states.POWERING_OFF
        instance.progress = 0
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance, instance_actions.STOP)

        self.compute_rpcapi.stop_instance(context, instance, do_cast=do_cast)

    @check_instance_lock
    @check_instance_host
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.ERROR])
    def stop(self, context, instance, do_cast=True):
        """Stop an instance."""
        self.force_stop(context, instance, do_cast)

    @check_instance_lock
    @check_instance_host
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.STOPPED])
    def start(self, context, instance):
        """Start an instance."""
        LOG.debug("Going to try to start instance", instance=instance)

        instance.task_state = task_states.POWERING_ON
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance, instance_actions.START)
        # TODO(yamahata): injected_files isn't supported right now.
        #                 It is used only for osapi. not for ec2 api.
        #                 availability_zone isn't used by run_instance.
        self.compute_rpcapi.start_instance(context, instance)

    def get(self, context, instance_id, want_objects=False,
            expected_attrs=None):
        """Get a single instance with the given instance_id."""
        if not expected_attrs:
            expected_attrs = []
        expected_attrs.extend(['metadata', 'system_metadata',
                               'security_groups', 'info_cache'])
        # NOTE(ameade): we still need to support integer ids for ec2
        try:
            if uuidutils.is_uuid_like(instance_id):
                instance = objects.Instance.get_by_uuid(
                    context, instance_id, expected_attrs=expected_attrs)
            elif utils.is_int_like(instance_id):
                instance = objects.Instance.get_by_id(
                    context, instance_id, expected_attrs=expected_attrs)
            else:
                raise exception.InstanceNotFound(instance_id=instance_id)
        except exception.InvalidID:
            raise exception.InstanceNotFound(instance_id=instance_id)

        check_policy(context, 'get', instance)

        if not want_objects:
            instance = obj_base.obj_to_primitive(instance)
        return instance

    def get_all(self, context, search_opts=None, sort_key='created_at',
                sort_dir='desc', limit=None, marker=None, want_objects=False,
                expected_attrs=None):
        """Get all instances filtered by one of the given parameters.

        If there is no filter and the context is an admin, it will retrieve
        all instances in the system.

        Deleted instances will be returned by default, unless there is a
        search option that says otherwise.

        The results will be returned sorted in the order specified by the
        'sort_dir' parameter using the key specified in the 'sort_key'
        parameter.
        """

        # TODO(bcwaldon): determine the best argument for target here
        target = {
            'project_id': context.project_id,
            'user_id': context.user_id,
        }

        check_policy(context, "get_all", target)

        if search_opts is None:
            search_opts = {}

        LOG.debug("Searching by: %s" % str(search_opts))

        # Fixups for the DB call
        filters = {}

        def _remap_flavor_filter(flavor_id):
            flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
            filters['instance_type_id'] = flavor.id

        def _remap_fixed_ip_filter(fixed_ip):
            # Turn fixed_ip into a regexp match. Since '.' matches
            # any character, we need to use regexp escaping for it.
            filters['ip'] = '^%s$' % fixed_ip.replace('.', '\\.')

        def _remap_metadata_filter(metadata):
            filters['metadata'] = jsonutils.loads(metadata)

        def _remap_system_metadata_filter(metadata):
            filters['system_metadata'] = jsonutils.loads(metadata)

        # search_option to filter_name mapping.
        filter_mapping = {
                'image': 'image_ref',
                'name': 'display_name',
                'tenant_id': 'project_id',
                'flavor': _remap_flavor_filter,
                'fixed_ip': _remap_fixed_ip_filter,
                'metadata': _remap_metadata_filter,
                'system_metadata': _remap_system_metadata_filter}

        # copy from search_opts, doing various remappings as necessary
        for opt, value in search_opts.iteritems():
            # Do remappings.
            # Values not in the filter_mapping table are copied as-is.
            # If remapping is None, option is not copied
            # If the remapping is a string, it is the filter_name to use
            try:
                remap_object = filter_mapping[opt]
            except KeyError:
                filters[opt] = value
            else:
                # Remaps are strings to translate to, or functions to call
                # to do the translating as defined by the table above.
                if isinstance(remap_object, six.string_types):
                    filters[remap_object] = value
                else:
                    try:
                        remap_object(value)

                    # We already know we can't match the filter, so
                    # return an empty list
                    except ValueError:
                        return []

        inst_models = self._get_instances_by_filters(context, filters,
                sort_key, sort_dir, limit=limit, marker=marker,
                expected_attrs=expected_attrs)

        if 'ip6' in filters or 'ip' in filters:
            inst_models = self._ip_filter(inst_models, filters)

        if want_objects:
            return inst_models

        # Convert the models to dictionaries
        instances = []
        for inst_model in inst_models:
            instances.append(obj_base.obj_to_primitive(inst_model))

        return instances

    @staticmethod
    def _ip_filter(inst_models, filters):
        ipv4_f = re.compile(str(filters.get('ip')))
        ipv6_f = re.compile(str(filters.get('ip6')))
        result_objs = []
        for instance in inst_models:
            nw_info = compute_utils.get_nw_info_for_instance(instance)
            for vif in nw_info:
                for fixed_ip in vif.fixed_ips():
                    address = fixed_ip.get('address')
                    if not address:
                        continue
                    version = fixed_ip.get('version')
                    if ((version == 4 and ipv4_f.match(address)) or
                        (version == 6 and ipv6_f.match(address))):
                        result_objs.append(instance)
                        continue
        return objects.InstanceList(objects=result_objs)

    def _get_instances_by_filters(self, context, filters,
                                  sort_key, sort_dir,
                                  limit=None,
                                  marker=None, expected_attrs=None):
        fields = ['metadata', 'system_metadata', 'info_cache',
                  'security_groups']
        if expected_attrs:
            fields.extend(expected_attrs)
        return objects.InstanceList.get_by_filters(
            context, filters=filters, sort_key=sort_key, sort_dir=sort_dir,
            limit=limit, marker=marker, expected_attrs=fields)

    # NOTE(melwitt): We don't check instance lock for backup because lock is
    #                intended to prevent accidental change/delete of instances
    @wrap_check_policy
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED])
    def backup(self, context, instance, name, backup_type, rotation,
               extra_properties=None):
        """Backup the given instance

        :param instance: nova.db.sqlalchemy.models.Instance
        :param name: name of the backup
        :param backup_type: 'daily' or 'weekly'
        :param rotation: int representing how many backups to keep around;
            None if rotation shouldn't be used (as in the case of snapshots)
        :param extra_properties: dict of extra image properties to include
                                 when creating the image.
        :returns: A dict containing image metadata
        """
        props_copy = dict(extra_properties, backup_type=backup_type)
        image_meta = self._create_image(context, instance, name,
                                       'backup', extra_properties=props_copy)

        # NOTE(comstud): Any changes to this method should also be made
        # to the backup_instance() method in nova/cells/messaging.py

        instance.task_state = task_states.IMAGE_BACKUP
        instance.save(expected_task_state=[None])

        self.compute_rpcapi.backup_instance(context, instance,
                                            image_meta['id'],
                                            backup_type,
                                            rotation)
        return image_meta

    # NOTE(melwitt): We don't check instance lock for snapshot because lock is
    #                intended to prevent accidental change/delete of instances
    @wrap_check_policy
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED,
                                    vm_states.PAUSED, vm_states.SUSPENDED])
    def snapshot(self, context, instance, name, extra_properties=None):
        """Snapshot the given instance.

        :param instance: nova.db.sqlalchemy.models.Instance
        :param name: name of the snapshot
        :param extra_properties: dict of extra image properties to include
                                 when creating the image.
        :returns: A dict containing image metadata
        """
        image_meta = self._create_image(context, instance, name,
                                        'snapshot',
                                        extra_properties=extra_properties)

        # NOTE(comstud): Any changes to this method should also be made
        # to the snapshot_instance() method in nova/cells/messaging.py
        instance.task_state = task_states.IMAGE_SNAPSHOT_PENDING
        instance.save(expected_task_state=[None])

        self.compute_rpcapi.snapshot_instance(context, instance,
                                              image_meta['id'])

        return image_meta

    def _create_image(self, context, instance, name, image_type,
                      extra_properties=None):
        """Create new image entry in the image service.  This new image
        will be reserved for the compute manager to upload a snapshot
        or backup.

        :param context: security context
        :param instance: nova.db.sqlalchemy.models.Instance
        :param name: string for name of the snapshot
        :param image_type: snapshot | backup
        :param extra_properties: dict of extra image properties to include

        """
        if extra_properties is None:
            extra_properties = {}
        instance_uuid = instance['uuid']

        properties = {
            'instance_uuid': instance_uuid,
            'user_id': str(context.user_id),
            'image_type': image_type,
        }
        image_ref = instance.image_ref
        sent_meta = compute_utils.get_image_metadata(
            context, self.image_api, image_ref, instance)

        sent_meta['name'] = name
        sent_meta['is_public'] = False

        # The properties set up above and in extra_properties have precedence
        properties.update(extra_properties or {})
        sent_meta['properties'].update(properties)

        return self.image_api.create(context, sent_meta)

    # NOTE(melwitt): We don't check instance lock for snapshot because lock is
    #                intended to prevent accidental change/delete of instances
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED])
    def snapshot_volume_backed(self, context, instance, image_meta, name,
                               extra_properties=None):
        """Snapshot the given volume-backed instance.

        :param instance: nova.db.sqlalchemy.models.Instance
        :param image_meta: metadata for the new image
        :param name: name of the backup or snapshot
        :param extra_properties: dict of extra image properties to include

        :returns: the new image metadata
        """
        image_meta['name'] = name
        image_meta['is_public'] = False
        properties = image_meta['properties']
        if instance['root_device_name']:
            properties['root_device_name'] = instance['root_device_name']
        properties.update(extra_properties or {})

        bdms = objects.BlockDeviceMappingList.get_by_instance_uuid(
                context, instance['uuid'])

        mapping = []
        for bdm in bdms:
            if bdm.no_device:
                continue

            if bdm.is_volume:
                # create snapshot based on volume_id
                volume = self.volume_api.get(context, bdm.volume_id)
                # NOTE(yamahata): Should we wait for snapshot creation?
                #                 Linux LVM snapshot creation completes in
                #                 short time, it doesn't matter for now.
                name = _('snapshot for %s') % image_meta['name']
                snapshot = self.volume_api.create_snapshot_force(
                    context, volume['id'], name, volume['display_description'])
                mapping_dict = block_device.snapshot_from_bdm(snapshot['id'],
                                                              bdm)
                mapping_dict = mapping_dict.get_image_mapping()
            else:
                mapping_dict = bdm.get_image_mapping()

            mapping.append(mapping_dict)

        # NOTE (ndipanov): Remove swap/ephemerals from mappings as they will be
        # in the block_device_mapping for the new image.
        image_mappings = properties.get('mappings')
        if image_mappings:
            properties['mappings'] = [m for m in image_mappings
                                      if not block_device.is_swap_or_ephemeral(
                                          m['virtual'])]
        if mapping:
            properties['block_device_mapping'] = mapping
            properties['bdm_v2'] = True

        for attr in ('status', 'location', 'id', 'owner'):
            image_meta.pop(attr, None)

        # the new image is simply a bucket of properties (particularly the
        # block device mapping, kernel and ramdisk IDs) with no image data,
        # hence the zero size
        image_meta['size'] = 0

        return self.image_api.create(context, image_meta)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=set(
                    vm_states.ALLOW_SOFT_REBOOT + vm_states.ALLOW_HARD_REBOOT),
                          task_state=[None, task_states.REBOOTING,
                                      task_states.REBOOT_PENDING,
                                      task_states.REBOOT_STARTED,
                                      task_states.REBOOTING_HARD,
                                      task_states.RESUMING,
                                      task_states.UNPAUSING,
                                      task_states.PAUSING,
                                      task_states.SUSPENDING])
    def reboot(self, context, instance, reboot_type):
        """Reboot the given instance."""
        if (reboot_type == 'SOFT' and
            (instance['vm_state'] not in vm_states.ALLOW_SOFT_REBOOT)):
            raise exception.InstanceInvalidState(
                attr='vm_state',
                instance_uuid=instance['uuid'],
                state=instance['vm_state'],
                method='soft reboot')
        if ((reboot_type == 'SOFT' and
                instance['task_state'] in
                (task_states.REBOOTING, task_states.REBOOTING_HARD,
                 task_states.REBOOT_PENDING, task_states.REBOOT_STARTED)) or
            (reboot_type == 'HARD' and
                instance['task_state'] == task_states.REBOOTING_HARD)):
            raise exception.InstanceInvalidState(
                attr='task_state',
                instance_uuid=instance['uuid'],
                state=instance['task_state'],
                method='reboot')
        state = {'SOFT': task_states.REBOOTING,
                 'HARD': task_states.REBOOTING_HARD}[reboot_type]
        instance.task_state = state
        instance.save(expected_task_state=[None, task_states.REBOOTING,
                                           task_states.REBOOT_PENDING,
                                           task_states.REBOOT_STARTED])

        self._record_action_start(context, instance, instance_actions.REBOOT)

        self.compute_rpcapi.reboot_instance(context, instance=instance,
                                            block_device_info=None,
                                            reboot_type=reboot_type)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED,
                                    vm_states.ERROR])
    def rebuild(self, context, instance, image_href, admin_password,
                files_to_inject=None, **kwargs):
        """Rebuild the given instance with the provided attributes."""
        orig_image_ref = instance.image_ref or ''
        files_to_inject = files_to_inject or []
        metadata = kwargs.get('metadata', {})
        preserve_ephemeral = kwargs.get('preserve_ephemeral', False)
        auto_disk_config = kwargs.get('auto_disk_config')

        image_id, image = self._get_image(context, image_href)
        self._check_auto_disk_config(image=image, **kwargs)

        flavor = instance.get_flavor()
        self._checks_for_create_and_rebuild(context, image_id, image,
                flavor, metadata, files_to_inject)

        kernel_id, ramdisk_id = self._handle_kernel_and_ramdisk(
                context, None, None, image)

        def _reset_image_metadata():
            """Remove old image properties that we're storing as instance
            system metadata.  These properties start with 'image_'.
            Then add the properties for the new image.
            """
            # FIXME(comstud): There's a race condition here in that if
            # the system_metadata for this instance is updated after
            # we do the previous save() and before we update.. those
            # other updates will be lost. Since this problem exists in
            # a lot of other places, I think it should be addressed in
            # a DB layer overhaul.

            orig_sys_metadata = dict(instance.system_metadata)
            # Remove the old keys
            for key in instance.system_metadata.keys():
                if key.startswith(utils.SM_IMAGE_PROP_PREFIX):
                    del instance.system_metadata[key]

            # Add the new ones
            new_sys_metadata = utils.get_system_metadata_from_image(
                image, flavor)

            instance.system_metadata.update(new_sys_metadata)
            instance.save()
            return orig_sys_metadata

        # Since image might have changed, we may have new values for
        # os_type, vm_mode, etc
        options_from_image = self._inherit_properties_from_image(
                image, auto_disk_config)
        instance.update(options_from_image)

        instance.task_state = task_states.REBUILDING
        instance.image_ref = image_href
        instance.kernel_id = kernel_id or ""
        instance.ramdisk_id = ramdisk_id or ""
        instance.progress = 0
        instance.update(kwargs)
        instance.save(expected_task_state=[None])

        # On a rebuild, since we're potentially changing images, we need to
        # wipe out the old image properties that we're storing as instance
        # system metadata... and copy in the properties for the new image.
        orig_sys_metadata = _reset_image_metadata()

        bdms = objects.BlockDeviceMappingList.get_by_instance_uuid(
                context, instance.uuid)

        self._record_action_start(context, instance, instance_actions.REBUILD)

        self.compute_task_api.rebuild_instance(context, instance=instance,
                new_pass=admin_password, injected_files=files_to_inject,
                image_ref=image_href, orig_image_ref=orig_image_ref,
                orig_sys_metadata=orig_sys_metadata, bdms=bdms,
                preserve_ephemeral=preserve_ephemeral, host=instance.host,
                kwargs=kwargs)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.RESIZED])
    def revert_resize(self, context, instance):
        """Reverts a resize, deleting the 'new' instance in the process."""
        elevated = context.elevated()
        migration = objects.Migration.get_by_instance_and_status(
            elevated, instance.uuid, 'finished')

        # reverse quota reservation for increased resource usage
        deltas = self._reverse_upsize_quota_delta(context, migration)
        quotas = self._reserve_quota_delta(context, deltas, instance)

        instance.task_state = task_states.RESIZE_REVERTING
        try:
            instance.save(expected_task_state=[None])
        except Exception:
            with excutils.save_and_reraise_exception():
                quotas.rollback(context)

        migration.status = 'reverting'
        migration.save()
        # With cells, the best we can do right now is commit the reservations
        # immediately...
        if CONF.cells.enable:
            quotas.commit(context)

        self._record_action_start(context, instance,
                                  instance_actions.REVERT_RESIZE)

        self.compute_rpcapi.revert_resize(context, instance,
                                          migration,
                                          migration.dest_compute,
                                          quotas.reservations or [])

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.RESIZED])
    def confirm_resize(self, context, instance, migration=None):
        """Confirms a migration/resize and deletes the 'old' instance."""
        elevated = context.elevated()
        if migration is None:
            migration = objects.Migration.get_by_instance_and_status(
                elevated, instance.uuid, 'finished')

        # reserve quota only for any decrease in resource usage
        deltas = self._downsize_quota_delta(context, instance)
        quotas = self._reserve_quota_delta(context, deltas, instance)

        migration.status = 'confirming'
        migration.save()
        # With cells, the best we can do right now is commit the reservations
        # immediately...
        if CONF.cells.enable:
            quotas.commit(context)

        self._record_action_start(context, instance,
                                  instance_actions.CONFIRM_RESIZE)

        self.compute_rpcapi.confirm_resize(context,
                                           instance,
                                           migration,
                                           migration.source_compute,
                                           quotas.reservations or [])

    @staticmethod
    def _resize_quota_delta(context, new_flavor,
                            old_flavor, sense, compare):
        """Calculate any quota adjustment required at a particular point
        in the resize cycle.

        :param context: the request context
        :param new_instance_type: the target instance type
        :param old_instance_type: the original instance type
        :param sense: the sense of the adjustment, 1 indicates a
                      forward adjustment, whereas -1 indicates a
                      reversal of a prior adjustment
        :param compare: the direction of the comparison, 1 indicates
                        we're checking for positive deltas, whereas
                        -1 indicates negative deltas
        """
        def _quota_delta(resource):
            return sense * (new_flavor[resource] - old_flavor[resource])

        deltas = {}
        if compare * _quota_delta('vcpus') > 0:
            deltas['cores'] = _quota_delta('vcpus')
        if compare * _quota_delta('memory_mb') > 0:
            deltas['ram'] = _quota_delta('memory_mb')

        return deltas

    @staticmethod
    def _upsize_quota_delta(context, new_flavor, old_flavor):
        """Calculate deltas required to adjust quota for an instance upsize.
        """
        return API._resize_quota_delta(context, new_flavor, old_flavor, 1, 1)

    @staticmethod
    def _reverse_upsize_quota_delta(context, migration_ref):
        """Calculate deltas required to reverse a prior upsizing
        quota adjustment.
        """
        old_flavor = objects.Flavor.get_by_id(
            context, migration_ref['old_instance_type_id'])
        new_flavor = objects.Flavor.get_by_id(
            context, migration_ref['new_instance_type_id'])

        return API._resize_quota_delta(context, new_flavor, old_flavor, -1, -1)

    @staticmethod
    def _downsize_quota_delta(context, instance):
        """Calculate deltas required to adjust quota for an instance downsize.
        """
        old_flavor = instance.get_flavor('old')
        new_flavor = instance.get_flavor('new')
        return API._resize_quota_delta(context, new_flavor, old_flavor, 1, -1)

    @staticmethod
    def _reserve_quota_delta(context, deltas, instance):
        """If there are deltas to reserve, construct a Quotas object and
        reserve the deltas for the given project.

        @param context:    The nova request context.
        @param deltas:     A dictionary of the proposed delta changes.
        @param instance:   The instance we're operating on, so that
                           quotas can use the correct project_id/user_id.
        @return: nova.objects.quotas.Quotas
        """
        quotas = objects.Quotas()
        if deltas:
            project_id, user_id = quotas_obj.ids_from_instance(context,
                                                               instance)
            quotas.reserve(context, project_id=project_id, user_id=user_id,
                           **deltas)
        return quotas

    @staticmethod
    def _resize_cells_support(context, quotas, instance,
                              current_instance_type, new_instance_type):
        """Special API cell logic for resize."""
        # With cells, the best we can do right now is commit the
        # reservations immediately...
        quotas.commit(context)
        # NOTE(johannes/comstud): The API cell needs a local migration
        # record for later resize_confirm and resize_reverts to deal
        # with quotas.  We don't need source and/or destination
        # information, just the old and new flavors. Status is set to
        # 'finished' since nothing else will update the status along
        # the way.
        mig = objects.Migration()
        mig.instance_uuid = instance.uuid
        mig.old_instance_type_id = current_instance_type['id']
        mig.new_instance_type_id = new_instance_type['id']
        mig.status = 'finished'
        mig.create(context.elevated())

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED])
    def resize(self, context, instance, flavor_id=None,
               **extra_instance_updates):
        """Resize (ie, migrate) a running instance.

        If flavor_id is None, the process is considered a migration, keeping
        the original flavor_id. If flavor_id is not None, the instance should
        be migrated to a new host and resized to the new flavor_id.
        """
        self._check_auto_disk_config(instance, **extra_instance_updates)

        current_instance_type = flavors.extract_flavor(instance)

        # If flavor_id is not provided, only migrate the instance.
        if not flavor_id:
            LOG.debug("flavor_id is None. Assuming migration.",
                      instance=instance)
            new_instance_type = current_instance_type
        else:
            new_instance_type = flavors.get_flavor_by_flavor_id(
                    flavor_id, read_deleted="no")
            if (new_instance_type.get('root_gb') == 0 and
                current_instance_type.get('root_gb') != 0):
                reason = _('Resize to zero disk flavor is not allowed.')
                raise exception.CannotResizeDisk(reason=reason)

        if not new_instance_type:
            raise exception.FlavorNotFound(flavor_id=flavor_id)

        current_instance_type_name = current_instance_type['name']
        new_instance_type_name = new_instance_type['name']
        LOG.debug("Old instance type %(current_instance_type_name)s, "
                  " new instance type %(new_instance_type_name)s",
                  {'current_instance_type_name': current_instance_type_name,
                   'new_instance_type_name': new_instance_type_name},
                  instance=instance)

        same_instance_type = (current_instance_type['id'] ==
                              new_instance_type['id'])

        # NOTE(sirp): We don't want to force a customer to change their flavor
        # when Ops is migrating off of a failed host.
        if not same_instance_type and new_instance_type.get('disabled'):
            raise exception.FlavorNotFound(flavor_id=flavor_id)

        if same_instance_type and flavor_id and self.cell_type != 'compute':
            raise exception.CannotResizeToSameFlavor()

        # ensure there is sufficient headroom for upsizes
        deltas = self._upsize_quota_delta(context, new_instance_type,
                                          current_instance_type)
        try:
            quotas = self._reserve_quota_delta(context, deltas, instance)
        except exception.OverQuota as exc:
            quotas = exc.kwargs['quotas']
            overs = exc.kwargs['overs']
            headroom = exc.kwargs['headroom']

            resource = overs[0]
            used = quotas[resource] - headroom[resource]
            total_allowed = used + headroom[resource]
            overs = ','.join(overs)
            LOG.warn(_("%(overs)s quota exceeded for %(pid)s,"
                       " tried to resize instance."),
                     {'overs': overs, 'pid': context.project_id})
            raise exception.TooManyInstances(overs=overs,
                                             req=deltas[resource],
                                             used=used, allowed=total_allowed,
                                             resource=resource)

        instance.task_state = task_states.RESIZE_PREP
        instance.progress = 0
        instance.update(extra_instance_updates)
        instance.save(expected_task_state=[None])

        filter_properties = {'ignore_hosts': []}

        if not CONF.allow_resize_to_same_host:
            filter_properties['ignore_hosts'].append(instance['host'])

        # Here when flavor_id is None, the process is considered as migrate.
        if (not flavor_id and not CONF.allow_migrate_to_same_host):
            filter_properties['ignore_hosts'].append(instance['host'])

        if self.cell_type == 'api':
            # Commit reservations early and create migration record.
            self._resize_cells_support(context, quotas, instance,
                                       current_instance_type,
                                       new_instance_type)

        if not flavor_id:
            self._record_action_start(context, instance,
                                      instance_actions.MIGRATE)
        else:
            self._record_action_start(context, instance,
                                      instance_actions.RESIZE)

        scheduler_hint = {'filter_properties': filter_properties}
        self.compute_task_api.resize_instance(context, instance,
                extra_instance_updates, scheduler_hint=scheduler_hint,
                flavor=new_instance_type,
                reservations=quotas.reservations or [])

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED,
                                    vm_states.PAUSED, vm_states.SUSPENDED])
    def shelve(self, context, instance):
        """Shelve an instance.

        Shuts down an instance and frees it up to be removed from the
        hypervisor.
        """
        instance.task_state = task_states.SHELVING
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance, instance_actions.SHELVE)

        image_id = None
        if not self.is_volume_backed_instance(context, instance):
            name = '%s-shelved' % instance['display_name']
            image_meta = self._create_image(context, instance, name,
                    'snapshot')
            image_id = image_meta['id']
            self.compute_rpcapi.shelve_instance(context, instance=instance,
                    image_id=image_id)
        else:
            self.compute_rpcapi.shelve_offload_instance(context,
                    instance=instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.SHELVED])
    def shelve_offload(self, context, instance):
        """Remove a shelved instance from the hypervisor."""
        instance.task_state = task_states.SHELVING_OFFLOADING
        instance.save(expected_task_state=[None])

        self.compute_rpcapi.shelve_offload_instance(context, instance=instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.SHELVED,
        vm_states.SHELVED_OFFLOADED])
    def unshelve(self, context, instance):
        """Restore a shelved instance."""
        instance.task_state = task_states.UNSHELVING
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance, instance_actions.UNSHELVE)

        self.compute_task_api.unshelve_instance(context, instance)

    @wrap_check_policy
    @check_instance_lock
    def add_fixed_ip(self, context, instance, network_id):
        """Add fixed_ip from specified network to given instance."""
        self.compute_rpcapi.add_fixed_ip_to_instance(context,
                instance=instance, network_id=network_id)

    @wrap_check_policy
    @check_instance_lock
    def remove_fixed_ip(self, context, instance, address):
        """Remove fixed_ip from specified network to given instance."""
        self.compute_rpcapi.remove_fixed_ip_from_instance(context,
                instance=instance, address=address)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE])
    def pause(self, context, instance):
        """Pause the given instance."""
        instance.task_state = task_states.PAUSING
        instance.save(expected_task_state=[None])
        self._record_action_start(context, instance, instance_actions.PAUSE)
        self.compute_rpcapi.pause_instance(context, instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.PAUSED])
    def unpause(self, context, instance):
        """Unpause the given instance."""
        instance.task_state = task_states.UNPAUSING
        instance.save(expected_task_state=[None])
        self._record_action_start(context, instance, instance_actions.UNPAUSE)
        self.compute_rpcapi.unpause_instance(context, instance)

    @wrap_check_policy
    def get_diagnostics(self, context, instance):
        """Retrieve diagnostics for the given instance."""
        return self.compute_rpcapi.get_diagnostics(context, instance=instance)

    @wrap_check_policy
    def get_instance_diagnostics(self, context, instance):
        """Retrieve diagnostics for the given instance."""
        return self.compute_rpcapi.get_instance_diagnostics(context,
                                                            instance=instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE])
    def suspend(self, context, instance):
        """Suspend the given instance."""
        instance.task_state = task_states.SUSPENDING
        instance.save(expected_task_state=[None])
        self._record_action_start(context, instance, instance_actions.SUSPEND)
        self.compute_rpcapi.suspend_instance(context, instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.SUSPENDED])
    def resume(self, context, instance):
        """Resume the given instance."""
        instance.task_state = task_states.RESUMING
        instance.save(expected_task_state=[None])
        self._record_action_start(context, instance, instance_actions.RESUME)
        self.compute_rpcapi.resume_instance(context, instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED,
                                    vm_states.ERROR])
    def rescue(self, context, instance, rescue_password=None,
               rescue_image_ref=None):
        """Rescue the given instance."""

        bdms = objects.BlockDeviceMappingList.get_by_instance_uuid(
                    context, instance.uuid)
        for bdm in bdms:
            if bdm.volume_id:
                vol = self.volume_api.get(context, bdm.volume_id)
                self.volume_api.check_attached(context, vol)
        if self.is_volume_backed_instance(context, instance, bdms):
            reason = _("Cannot rescue a volume-backed instance")
            raise exception.InstanceNotRescuable(instance_id=instance.uuid,
                                                 reason=reason)

        instance.task_state = task_states.RESCUING
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance, instance_actions.RESCUE)

        self.compute_rpcapi.rescue_instance(context, instance=instance,
            rescue_password=rescue_password, rescue_image_ref=rescue_image_ref)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.RESCUED])
    def unrescue(self, context, instance):
        """Unrescue the given instance."""
        instance.task_state = task_states.UNRESCUING
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance, instance_actions.UNRESCUE)

        self.compute_rpcapi.unrescue_instance(context, instance=instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE])
    def set_admin_password(self, context, instance, password=None):
        """Set the root/admin password for the given instance.

        @param context: Nova auth context.
        @param instance: Nova instance object.
        @param password: The admin password for the instance.
        """
        instance.task_state = task_states.UPDATING_PASSWORD
        instance.save(expected_task_state=[None])

        self._record_action_start(context, instance,
                                  instance_actions.CHANGE_PASSWORD)

        self.compute_rpcapi.set_admin_password(context,
                                               instance=instance,
                                               new_pass=password)

    @wrap_check_policy
    @check_instance_host
    def get_vnc_console(self, context, instance, console_type):
        """Get a url to an instance Console."""
        connect_info = self.compute_rpcapi.get_vnc_console(context,
                instance=instance, console_type=console_type)

        self.consoleauth_rpcapi.authorize_console(context,
                connect_info['token'], console_type,
                connect_info['host'], connect_info['port'],
                connect_info['internal_access_path'], instance['uuid'])

        return {'url': connect_info['access_url']}

    @check_instance_host
    def get_vnc_connect_info(self, context, instance, console_type):
        """Used in a child cell to get console info."""
        connect_info = self.compute_rpcapi.get_vnc_console(context,
                instance=instance, console_type=console_type)
        return connect_info

    @wrap_check_policy
    @check_instance_host
    def get_spice_console(self, context, instance, console_type):
        """Get a url to an instance Console."""
        connect_info = self.compute_rpcapi.get_spice_console(context,
                instance=instance, console_type=console_type)
        self.consoleauth_rpcapi.authorize_console(context,
                connect_info['token'], console_type,
                connect_info['host'], connect_info['port'],
                connect_info['internal_access_path'], instance['uuid'])

        return {'url': connect_info['access_url']}

    @check_instance_host
    def get_spice_connect_info(self, context, instance, console_type):
        """Used in a child cell to get console info."""
        connect_info = self.compute_rpcapi.get_spice_console(context,
                instance=instance, console_type=console_type)
        return connect_info

    @wrap_check_policy
    @check_instance_host
    def get_rdp_console(self, context, instance, console_type):
        """Get a url to an instance Console."""
        connect_info = self.compute_rpcapi.get_rdp_console(context,
                instance=instance, console_type=console_type)
        self.consoleauth_rpcapi.authorize_console(context,
                connect_info['token'], console_type,
                connect_info['host'], connect_info['port'],
                connect_info['internal_access_path'], instance['uuid'])

        return {'url': connect_info['access_url']}

    @check_instance_host
    def get_rdp_connect_info(self, context, instance, console_type):
        """Used in a child cell to get console info."""
        connect_info = self.compute_rpcapi.get_rdp_console(context,
                instance=instance, console_type=console_type)
        return connect_info

    @wrap_check_policy
    @check_instance_host
    def get_serial_console(self, context, instance, console_type):
        """Get a url to a serial console."""
        connect_info = self.compute_rpcapi.get_serial_console(context,
                instance=instance, console_type=console_type)

        self.consoleauth_rpcapi.authorize_console(context,
                connect_info['token'], console_type,
                connect_info['host'], connect_info['port'],
                connect_info['internal_access_path'], instance['uuid'])
        return {'url': connect_info['access_url']}

    @check_instance_host
    def get_serial_console_connect_info(self, context, instance, console_type):
        """Used in a child cell to get serial console."""
        connect_info = self.compute_rpcapi.get_serial_console(context,
                instance=instance, console_type=console_type)
        return connect_info

    @wrap_check_policy
    @check_instance_host
    def get_console_output(self, context, instance, tail_length=None):
        """Get console output for an instance."""
        return self.compute_rpcapi.get_console_output(context,
                instance=instance, tail_length=tail_length)

    @wrap_check_policy
    def lock(self, context, instance):
        """Lock the given instance."""
        # Only update the lock if we are an admin (non-owner)
        is_owner = instance.project_id == context.project_id
        if instance.locked and is_owner:
            return

        context = context.elevated()
        LOG.debug('Locking', context=context, instance=instance)
        instance.locked = True
        instance.locked_by = 'owner' if is_owner else 'admin'
        instance.save()

    @wrap_check_policy
    def unlock(self, context, instance):
        """Unlock the given instance."""
        # If the instance was locked by someone else, check
        # that we're allowed to override the lock
        is_owner = instance.project_id == context.project_id
        expect_locked_by = 'owner' if is_owner else 'admin'
        locked_by = instance.locked_by
        if locked_by and locked_by != expect_locked_by:
            check_policy(context, 'unlock_override', instance)

        context = context.elevated()
        LOG.debug('Unlocking', context=context, instance=instance)
        instance.locked = False
        instance.locked_by = None
        instance.save()

    @wrap_check_policy
    def get_lock(self, context, instance):
        """Return the boolean state of given instance's lock."""
        return self.get(context, instance['uuid'])['locked']

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    def reset_network(self, context, instance):
        """Reset networking on the instance."""
        self.compute_rpcapi.reset_network(context, instance=instance)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_cell
    def inject_network_info(self, context, instance):
        """Inject network info for the instance."""
        self.compute_rpcapi.inject_network_info(context, instance=instance)

    def _attach_volume(self, context, instance, volume_id, device,
                       disk_bus, device_type):
        """Attach an existing volume to an existing instance.

        This method is separated to make it possible for cells version
        to override it.
        """
        # NOTE(vish): This is done on the compute host because we want
        #             to avoid a race where two devices are requested at
        #             the same time. When db access is removed from
        #             compute, the bdm will be created here and we will
        #             have to make sure that they are assigned atomically.
        volume_bdm = self.compute_rpcapi.reserve_block_device_name(
            context, instance, device, volume_id, disk_bus=disk_bus,
            device_type=device_type)
        try:
            volume = self.volume_api.get(context, volume_id)
            self.volume_api.check_attach(context, volume, instance=instance)
            self.volume_api.reserve_volume(context, volume_id)
            self.compute_rpcapi.attach_volume(context, instance=instance,
                    volume_id=volume_id, mountpoint=device, bdm=volume_bdm)
        except Exception:
            with excutils.save_and_reraise_exception():
                volume_bdm.destroy(context)

        return volume_bdm.device_name

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.STOPPED, vm_states.RESIZED,
                                    vm_states.SOFT_DELETED])
    def attach_volume(self, context, instance, volume_id, device=None,
                       disk_bus=None, device_type=None):
        """Attach an existing volume to an existing instance."""
        # NOTE(vish): Fail fast if the device is not going to pass. This
        #             will need to be removed along with the test if we
        #             change the logic in the manager for what constitutes
        #             a valid device.
        if device and not block_device.match_device(device):
            raise exception.InvalidDevicePath(path=device)
        return self._attach_volume(context, instance, volume_id, device,
                                   disk_bus, device_type)

    def _detach_volume(self, context, instance, volume):
        """Detach volume from instance.

        This method is separated to make it easier for cells version
        to override.
        """
        self.volume_api.check_detach(context, volume)
        self.volume_api.begin_detaching(context, volume['id'])
        self.compute_rpcapi.detach_volume(context, instance=instance,
                volume_id=volume['id'])

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.STOPPED, vm_states.RESIZED,
                                    vm_states.SOFT_DELETED])
    def detach_volume(self, context, instance, volume):
        """Detach a volume from an instance."""
        if volume['attach_status'] == 'detached':
            msg = _("Volume must be attached in order to detach.")
            raise exception.InvalidVolume(reason=msg)
        # The caller likely got the instance from volume['instance_uuid']
        # in the first place, but let's sanity check.
        if volume['instance_uuid'] != instance['uuid']:
            raise exception.VolumeUnattached(volume_id=volume['id'])
        self._detach_volume(context, instance, volume)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.SUSPENDED, vm_states.STOPPED,
                                    vm_states.RESIZED, vm_states.SOFT_DELETED])
    def swap_volume(self, context, instance, old_volume, new_volume):
        """Swap volume attached to an instance."""
        if old_volume['attach_status'] == 'detached':
            raise exception.VolumeUnattached(volume_id=old_volume['id'])
        # The caller likely got the instance from volume['instance_uuid']
        # in the first place, but let's sanity check.
        if old_volume['instance_uuid'] != instance['uuid']:
            msg = _("Old volume is attached to a different instance.")
            raise exception.InvalidVolume(reason=msg)
        if new_volume['attach_status'] == 'attached':
            msg = _("New volume must be detached in order to swap.")
            raise exception.InvalidVolume(reason=msg)
        if int(new_volume['size']) < int(old_volume['size']):
            msg = _("New volume must be the same size or larger.")
            raise exception.InvalidVolume(reason=msg)
        self.volume_api.check_detach(context, old_volume)
        self.volume_api.check_attach(context, new_volume, instance=instance)
        self.volume_api.begin_detaching(context, old_volume['id'])
        self.volume_api.reserve_volume(context, new_volume['id'])
        try:
            self.compute_rpcapi.swap_volume(
                    context, instance=instance,
                    old_volume_id=old_volume['id'],
                    new_volume_id=new_volume['id'])
        except Exception:  # pylint: disable=W0702
            with excutils.save_and_reraise_exception():
                self.volume_api.roll_detaching(context, old_volume['id'])
                self.volume_api.unreserve_volume(context, new_volume['id'])

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.STOPPED],
                          task_state=[None])
    def attach_interface(self, context, instance, network_id, port_id,
                         requested_ip):
        """Use hotplug to add an network adapter to an instance."""
        return self.compute_rpcapi.attach_interface(context,
            instance=instance, network_id=network_id, port_id=port_id,
            requested_ip=requested_ip)

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.STOPPED],
                          task_state=[None])
    def detach_interface(self, context, instance, port_id):
        """Detach an network adapter from an instance."""
        self.compute_rpcapi.detach_interface(context, instance=instance,
            port_id=port_id)

    @wrap_check_policy
    def get_instance_metadata(self, context, instance):
        """Get all metadata associated with an instance."""
        rv = self.db.instance_metadata_get(context, instance['uuid'])
        return dict(rv.iteritems())

    def get_all_instance_metadata(self, context, search_filts):
        return self._get_all_instance_metadata(
            context, search_filts, metadata_type='metadata')

    def get_all_system_metadata(self, context, search_filts):
        return self._get_all_instance_metadata(
            context, search_filts, metadata_type='system_metadata')

    def _get_all_instance_metadata(self, context, search_filts, metadata_type):
        """Get all metadata."""

        def _match_any(pattern_list, string):
            return any([re.match(pattern, string)
                        for pattern in pattern_list])

        def _filter_metadata(instance, search_filt, input_metadata):
            uuids = search_filt.get('resource_id', [])
            keys_filter = search_filt.get('key', [])
            values_filter = search_filt.get('value', [])
            output_metadata = {}

            if uuids and instance.get('uuid') not in uuids:
                return {}

            for (k, v) in input_metadata.iteritems():
                # Both keys and value defined -- AND
                if ((keys_filter and values_filter) and
                   not _match_any(keys_filter, k) and
                   not _match_any(values_filter, v)):
                    continue
                # Only keys or value is defined
                elif ((keys_filter and not _match_any(keys_filter, k)) or
                      (values_filter and not _match_any(values_filter, v))):
                    continue

                output_metadata[k] = v
            return output_metadata

        formatted_metadata_list = []
        instances = self._get_instances_by_filters(context, filters={},
                                                   sort_key='created_at',
                                                   sort_dir='desc')
        for instance in instances:
            try:
                check_policy(context, 'get_all_instance_%s' % metadata_type,
                             instance)
                metadata = instance.get(metadata_type, {})
                for filt in search_filts:
                    # By chaining the input to the output, the filters are
                    # ANDed together
                    metadata = _filter_metadata(instance, filt, metadata)

                for (k, v) in metadata.iteritems():
                    formatted_metadata_list.append({'key': k, 'value': v,
                                     'instance_id': instance.get('uuid')})
            except exception.PolicyNotAuthorized:
                # failed policy check - not allowed to
                # read this metadata
                continue

        return formatted_metadata_list

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.SUSPENDED, vm_states.STOPPED],
                          task_state=None)
    def delete_instance_metadata(self, context, instance, key):
        """Delete the given metadata item from an instance."""
        instance.delete_metadata_key(key)
        self.compute_rpcapi.change_instance_metadata(context,
                                                     instance=instance,
                                                     diff={key: ['-']})

    @wrap_check_policy
    @check_instance_lock
    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.PAUSED,
                                    vm_states.SUSPENDED, vm_states.STOPPED],
                          task_state=None)
    def update_instance_metadata(self, context, instance,
                                 metadata, delete=False):
        """Updates or creates instance metadata.

        If delete is True, metadata items that are not specified in the
        `metadata` argument will be deleted.

        """
        orig = dict(instance.metadata)
        if delete:
            _metadata = metadata
        else:
            _metadata = dict(instance.metadata)
            _metadata.update(metadata)

        self._check_metadata_properties_quota(context, _metadata)
        instance.metadata = _metadata
        instance.save()
        diff = _diff_dict(orig, instance.metadata)
        self.compute_rpcapi.change_instance_metadata(context,
                                                     instance=instance,
                                                     diff=diff)
        return _metadata

    def get_instance_faults(self, context, instances):
        """Get all faults for a list of instance uuids."""

        if not instances:
            return {}

        for instance in instances:
            check_policy(context, 'get_instance_faults', instance)

        uuids = [instance['uuid'] for instance in instances]
        return self.db.instance_fault_get_by_instance_uuids(context, uuids)

    def is_volume_backed_instance(self, context, instance, bdms=None):
        if not instance['image_ref']:
            return True

        if bdms is None:
            bdms = objects.BlockDeviceMappingList.get_by_instance_uuid(
                    context, instance['uuid'])

        root_bdm = bdms.root_bdm()
        if not root_bdm:
            return False
        return root_bdm.is_volume

    @check_instance_lock
    @check_instance_cell
    @check_instance_state(vm_state=[vm_states.ACTIVE])
    def live_migrate(self, context, instance, block_migration,
                     disk_over_commit, host_name):
        """Migrate a server lively to a new host."""
        LOG.debug("Going to try to live migrate instance to %s",
                  host_name or "another host", instance=instance)

        instance.task_state = task_states.MIGRATING
        instance.save(expected_task_state=[None])

        self.compute_task_api.live_migrate_instance(context, instance,
                host_name, block_migration=block_migration,
                disk_over_commit=disk_over_commit)

    @check_instance_state(vm_state=[vm_states.ACTIVE, vm_states.STOPPED,
                                    vm_states.ERROR])
    def evacuate(self, context, instance, host, on_shared_storage,
                 admin_password=None):
        """Running evacuate to target host.

        Checking vm compute host state, if the host not in expected_state,
        raising an exception.

        :param instance: The instance to evacuate
        :param host: Target host. if not set, the scheduler will pick up one
        :param on_shared_storage: True if instance files on shared storage
        :param admin_password: password to set on rebuilt instance

        """
        LOG.debug('vm evacuation scheduled', instance=instance)
        inst_host = instance.host
        service = objects.Service.get_by_compute_host(context, inst_host)
        if self.servicegroup_api.service_is_up(service):
            msg = (_('Instance compute service state on %s '
                     'expected to be down, but it was up.') % inst_host)
            LOG.error(msg)
            raise exception.ComputeServiceInUse(host=inst_host)

        instance.task_state = task_states.REBUILDING
        instance.save(expected_task_state=[None])
        self._record_action_start(context, instance, instance_actions.EVACUATE)

        return self.compute_task_api.rebuild_instance(context,
                       instance=instance,
                       new_pass=admin_password,
                       injected_files=None,
                       image_ref=None,
                       orig_image_ref=None,
                       orig_sys_metadata=None,
                       bdms=None,
                       recreate=True,
                       on_shared_storage=on_shared_storage,
                       host=host)

    def get_migrations(self, context, filters):
        """Get all migrations for the given filters."""
        return objects.MigrationList.get_by_filters(context, filters)

    @wrap_check_policy
    def volume_snapshot_create(self, context, volume_id, create_info):
        bdm = objects.BlockDeviceMapping.get_by_volume_id(
                context, volume_id, expected_attrs=['instance'])
        self.compute_rpcapi.volume_snapshot_create(context, bdm.instance,
                volume_id, create_info)
        snapshot = {
            'snapshot': {
                'id': create_info.get('id'),
                'volumeId': volume_id
            }
        }
        return snapshot

    @wrap_check_policy
    def volume_snapshot_delete(self, context, volume_id, snapshot_id,
                               delete_info):
        bdm = objects.BlockDeviceMapping.get_by_volume_id(
                context, volume_id, expected_attrs=['instance'])
        self.compute_rpcapi.volume_snapshot_delete(context, bdm.instance,
                volume_id, snapshot_id, delete_info)

    def external_instance_event(self, context, instances, events):
        # NOTE(danms): The external API consumer just provides events,
        # but doesn't know where they go. We need to collate lists
        # by the host the affected instance is on and dispatch them
        # according to host
        instances_by_host = {}
        events_by_host = {}
        hosts_by_instance = {}
        for instance in instances:
            instances_on_host = instances_by_host.get(instance.host, [])
            instances_on_host.append(instance)
            instances_by_host[instance.host] = instances_on_host
            hosts_by_instance[instance.uuid] = instance.host

        for event in events:
            host = hosts_by_instance[event.instance_uuid]
            events_on_host = events_by_host.get(host, [])
            events_on_host.append(event)
            events_by_host[host] = events_on_host

        for host in instances_by_host:
            # TODO(salv-orlando): Handle exceptions raised by the rpc api layer
            # in order to ensure that a failure in processing events on a host
            # will not prevent processing events on other hosts
            self.compute_rpcapi.external_instance_event(
                context, instances_by_host[host], events_by_host[host])


class HostAPI(base.Base):
    """Sub-set of the Compute Manager API for managing host operations."""

    def __init__(self, rpcapi=None):
        self.rpcapi = rpcapi or compute_rpcapi.ComputeAPI()
        self.servicegroup_api = servicegroup.API()
        super(HostAPI, self).__init__()

    def _assert_host_exists(self, context, host_name, must_be_up=False):
        """Raise HostNotFound if compute host doesn't exist."""
        service = objects.Service.get_by_compute_host(context, host_name)
        if not service:
            raise exception.HostNotFound(host=host_name)
        if must_be_up and not self.servicegroup_api.service_is_up(service):
            raise exception.ComputeServiceUnavailable(host=host_name)
        return service['host']

    @wrap_exception()
    def set_host_enabled(self, context, host_name, enabled):
        """Sets the specified host's ability to accept new instances."""
        host_name = self._assert_host_exists(context, host_name)
        payload = {'host_name': host_name, 'enabled': enabled}
        compute_utils.notify_about_host_update(context,
                                               'set_enabled.start',
                                               payload)
        result = self.rpcapi.set_host_enabled(context, enabled=enabled,
                host=host_name)
        compute_utils.notify_about_host_update(context,
                                               'set_enabled.end',
                                               payload)
        return result

    def get_host_uptime(self, context, host_name):
        """Returns the result of calling "uptime" on the target host."""
        host_name = self._assert_host_exists(context, host_name,
                         must_be_up=True)
        return self.rpcapi.get_host_uptime(context, host=host_name)

    @wrap_exception()
    def host_power_action(self, context, host_name, action):
        """Reboots, shuts down or powers up the host."""
        host_name = self._assert_host_exists(context, host_name)
        payload = {'host_name': host_name, 'action': action}
        compute_utils.notify_about_host_update(context,
                                               'power_action.start',
                                               payload)
        result = self.rpcapi.host_power_action(context, action=action,
                host=host_name)
        compute_utils.notify_about_host_update(context,
                                               'power_action.end',
                                               payload)
        return result

    @wrap_exception()
    def set_host_maintenance(self, context, host_name, mode):
        """Start/Stop host maintenance window. On start, it triggers
        guest VMs evacuation.
        """
        host_name = self._assert_host_exists(context, host_name)
        payload = {'host_name': host_name, 'mode': mode}
        compute_utils.notify_about_host_update(context,
                                               'set_maintenance.start',
                                               payload)
        result = self.rpcapi.host_maintenance_mode(context,
                host_param=host_name, mode=mode, host=host_name)
        compute_utils.notify_about_host_update(context,
                                               'set_maintenance.end',
                                               payload)
        return result

    def service_get_all(self, context, filters=None, set_zones=False):
        """Returns a list of services, optionally filtering the results.

        If specified, 'filters' should be a dictionary containing services
        attributes and matching values.  Ie, to get a list of services for
        the 'compute' topic, use filters={'topic': 'compute'}.
        """
        if filters is None:
            filters = {}
        disabled = filters.pop('disabled', None)
        if 'availability_zone' in filters:
            set_zones = True
        services = objects.ServiceList.get_all(context, disabled,
                                               set_zones=set_zones)
        ret_services = []
        for service in services:
            for key, val in filters.iteritems():
                if service[key] != val:
                    break
            else:
                # All filters matched.
                ret_services.append(service)
        return ret_services

    def service_get_by_compute_host(self, context, host_name):
        """Get service entry for the given compute hostname."""
        return objects.Service.get_by_compute_host(context, host_name)

    def service_update(self, context, host_name, binary, params_to_update):
        """Enable / Disable a service.

        For compute services, this stops new builds and migrations going to
        the host.
        """
        service = objects.Service.get_by_args(context, host_name, binary)
        service.update(params_to_update)
        service.save()
        return service

    def service_delete(self, context, service_id):
        """Deletes the specified service."""
        objects.Service.get_by_id(context, service_id).destroy()

    def instance_get_all_by_host(self, context, host_name):
        """Return all instances on the given host."""
        return self.db.instance_get_all_by_host(context, host_name)

    def task_log_get_all(self, context, task_name, period_beginning,
                         period_ending, host=None, state=None):
        """Return the task logs within a given range, optionally
        filtering by host and/or state.
        """
        return self.db.task_log_get_all(context, task_name,
                                        period_beginning,
                                        period_ending,
                                        host=host,
                                        state=state)

    def compute_node_get(self, context, compute_id):
        """Return compute node entry for particular integer ID."""
        return self.db.compute_node_get(context, int(compute_id))

    def compute_node_get_all(self, context):
        return self.db.compute_node_get_all(context)

    def compute_node_search_by_hypervisor(self, context, hypervisor_match):
        return self.db.compute_node_search_by_hypervisor(context,
                hypervisor_match)

    def compute_node_statistics(self, context):
        return self.db.compute_node_statistics(context)


class InstanceActionAPI(base.Base):
    """Sub-set of the Compute Manager API for managing instance actions."""

    def actions_get(self, context, instance):
        return objects.InstanceActionList.get_by_instance_uuid(
            context, instance['uuid'])

    def action_get_by_request_id(self, context, instance, request_id):
        return objects.InstanceAction.get_by_request_id(
            context, instance['uuid'], request_id)

    def action_events_get(self, context, instance, action_id):
        return objects.InstanceActionEventList.get_by_action(
            context, action_id)


class AggregateAPI(base.Base):
    """Sub-set of the Compute Manager API for managing host aggregates."""
    def __init__(self, **kwargs):
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        super(AggregateAPI, self).__init__(**kwargs)

    @wrap_exception()
    def create_aggregate(self, context, aggregate_name, availability_zone):
        """Creates the model for the aggregate."""

        aggregate = objects.Aggregate()
        aggregate.name = aggregate_name
        if availability_zone:
            aggregate.metadata = {'availability_zone': availability_zone}
        aggregate.create(context)

        aggregate = self._reformat_aggregate_info(aggregate)
        # To maintain the same API result as before.
        del aggregate['hosts']
        del aggregate['metadata']
        return aggregate

    def get_aggregate(self, context, aggregate_id):
        """Get an aggregate by id."""
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        return self._reformat_aggregate_info(aggregate)

    def get_aggregate_list(self, context):
        """Get all the aggregates."""
        aggregates = objects.AggregateList.get_all(context)
        return [self._reformat_aggregate_info(agg) for agg in aggregates]

    @wrap_exception()
    def update_aggregate(self, context, aggregate_id, values):
        """Update the properties of an aggregate."""
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        if 'name' in values:
            aggregate.name = values.pop('name')
            aggregate.save()
        self.is_safe_to_update_az(context, values, aggregate=aggregate,
                                  action_name="update_aggregate")
        if values:
            aggregate.update_metadata(values)
        # If updated values include availability_zones, then the cache
        # which stored availability_zones and host need to be reset
        if values.get('availability_zone'):
            availability_zones.reset_cache()
        return self._reformat_aggregate_info(aggregate)

    @wrap_exception()
    def update_aggregate_metadata(self, context, aggregate_id, metadata):
        """Updates the aggregate metadata."""
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        self.is_safe_to_update_az(context, metadata, aggregate=aggregate,
                                  action_name="update_aggregate_metadata")
        aggregate.update_metadata(metadata)
        # If updated metadata include availability_zones, then the cache
        # which stored availability_zones and host need to be reset
        if metadata and metadata.get('availability_zone'):
            availability_zones.reset_cache()
        return aggregate

    @wrap_exception()
    def delete_aggregate(self, context, aggregate_id):
        """Deletes the aggregate."""
        aggregate_payload = {'aggregate_id': aggregate_id}
        compute_utils.notify_about_aggregate_update(context,
                                                    "delete.start",
                                                    aggregate_payload)
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        if len(aggregate.hosts) > 0:
            msg = _("Host aggregate is not empty")
            raise exception.InvalidAggregateAction(action='delete',
                                                   aggregate_id=aggregate_id,
                                                   reason=msg)
        aggregate.destroy()
        compute_utils.notify_about_aggregate_update(context,
                                                    "delete.end",
                                                    aggregate_payload)

    def is_safe_to_update_az(self, context, metadata, aggregate,
                             hosts=None, action_name="add_host_to_aggregate"):
        """Determine if updates alter an aggregate's availability zone.

            :param context: local context
            :param metadata: Target metadata for updating aggregate
            :param aggregate: Aggregate to update
            :param hosts: Hosts to check. If None, aggregate.hosts is used
            :type hosts: list
            :action_name: Calling method for logging purposes

        """
        if 'availability_zone' in metadata:
            _hosts = hosts or aggregate.hosts
            zones, not_zones = availability_zones.get_availability_zones(
                context, with_hosts=True)
            for host in _hosts:
                # NOTE(sbauza): Host can only be in one AZ, so let's take only
                #               the first element
                host_azs = [az for (az, az_hosts) in zones
                            if host in az_hosts
                            and az != CONF.internal_service_availability_zone]
                host_az = host_azs.pop()
                if host_azs:
                    LOG.warning(_("More than 1 AZ for host %s"), host)
                if host_az == CONF.default_availability_zone:
                    # NOTE(sbauza): Aggregate with AZ set to default AZ can
                    #               exist, we need to check
                    host_aggs = objects.AggregateList.get_by_host(
                        context, host, key='availability_zone')
                    default_aggs = [agg for agg in host_aggs
                                    if agg['metadata'].get(
                                        'availability_zone'
                                    ) == CONF.default_availability_zone]
                else:
                    default_aggs = []
                if (host_az != aggregate.metadata.get('availability_zone') and
                        (host_az != CONF.default_availability_zone or
                            len(default_aggs) != 0)):
                                self._check_az_for_host(
                                    metadata, host_az, aggregate.id,
                                    action_name=action_name)

    def _check_az_for_host(self, aggregate_meta, host_az, aggregate_id,
                           action_name="add_host_to_aggregate"):
        # NOTE(mtreinish) The availability_zone key returns a set of
        # zones so loop over each zone. However there should only
        # ever be one zone in the set because an aggregate can only
        # have a single availability zone set at one time.
        if isinstance(aggregate_meta["availability_zone"], six.string_types):
            azs = set([aggregate_meta["availability_zone"]])
        else:
            azs = aggregate_meta["availability_zone"]

        for aggregate_az in azs:
            # NOTE(mtreinish) Ensure that the aggregate_az is not none
            # if it is none then that is just a regular aggregate and
            # it is valid to have a host in multiple aggregates.
            if aggregate_az and aggregate_az != host_az:
                msg = _("Host already in availability zone "
                        "%s") % host_az
                raise exception.InvalidAggregateAction(
                    action=action_name, aggregate_id=aggregate_id,
                    reason=msg)

    def _update_az_cache_for_host(self, context, host_name, aggregate_meta):
        # Update the availability_zone cache to avoid getting wrong
        # availability_zone in cache retention time when add/remove
        # host to/from aggregate.
        if aggregate_meta and aggregate_meta.get('availability_zone'):
            availability_zones.update_host_availability_zone_cache(context,
                                                                   host_name)

    @wrap_exception()
    def add_host_to_aggregate(self, context, aggregate_id, host_name):
        """Adds the host to an aggregate."""
        aggregate_payload = {'aggregate_id': aggregate_id,
                             'host_name': host_name}
        compute_utils.notify_about_aggregate_update(context,
                                                    "addhost.start",
                                                    aggregate_payload)
        # validates the host; ComputeHostNotFound is raised if invalid
        objects.Service.get_by_compute_host(context, host_name)

        metadata = self.db.aggregate_metadata_get_by_metadata_key(
            context, aggregate_id, 'availability_zone')
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        self.is_safe_to_update_az(context, metadata, hosts=[host_name],
                                  aggregate=aggregate)

        aggregate.add_host(context, host_name)
        self._update_az_cache_for_host(context, host_name, aggregate.metadata)
        # NOTE(jogo): Send message to host to support resource pools
        self.compute_rpcapi.add_aggregate_host(context,
                aggregate=aggregate, host_param=host_name, host=host_name)
        aggregate_payload.update({'name': aggregate['name']})
        compute_utils.notify_about_aggregate_update(context,
                                                    "addhost.end",
                                                    aggregate_payload)
        return self._reformat_aggregate_info(aggregate)

    @wrap_exception()
    def remove_host_from_aggregate(self, context, aggregate_id, host_name):
        """Removes host from the aggregate."""
        aggregate_payload = {'aggregate_id': aggregate_id,
                             'host_name': host_name}
        compute_utils.notify_about_aggregate_update(context,
                                                    "removehost.start",
                                                    aggregate_payload)
        # validates the host; ComputeHostNotFound is raised if invalid
        objects.Service.get_by_compute_host(context, host_name)
        aggregate = objects.Aggregate.get_by_id(context, aggregate_id)
        aggregate.delete_host(host_name)
        self._update_az_cache_for_host(context, host_name, aggregate.metadata)
        self.compute_rpcapi.remove_aggregate_host(context,
                aggregate=aggregate, host_param=host_name, host=host_name)
        compute_utils.notify_about_aggregate_update(context,
                                                    "removehost.end",
                                                    aggregate_payload)
        return self._reformat_aggregate_info(aggregate)

    def _reformat_aggregate_info(self, aggregate):
        """Builds a dictionary with aggregate props, metadata and hosts."""
        return dict(aggregate.iteritems())


class KeypairAPI(base.Base):
    """Subset of the Compute Manager API for managing key pairs."""

    get_notifier = functools.partial(rpc.get_notifier, service='api')
    wrap_exception = functools.partial(exception.wrap_exception,
                                       get_notifier=get_notifier)

    def _notify(self, context, event_suffix, keypair_name):
        payload = {
            'tenant_id': context.project_id,
            'user_id': context.user_id,
            'key_name': keypair_name,
        }
        notify = self.get_notifier()
        notify.info(context, 'keypair.%s' % event_suffix, payload)

    def _validate_new_key_pair(self, context, user_id, key_name):
        safe_chars = "_- " + string.digits + string.ascii_letters
        clean_value = "".join(x for x in key_name if x in safe_chars)
        if clean_value != key_name:
            raise exception.InvalidKeypair(
                reason=_("Keypair name contains unsafe characters"))

        try:
            utils.check_string_length(key_name, min_length=1, max_length=255)
        except exception.InvalidInput:
            raise exception.InvalidKeypair(
                reason=_('Keypair name must be string and between '
                         '1 and 255 characters long'))

        count = QUOTAS.count(context, 'key_pairs', user_id)
        try:
            QUOTAS.limit_check(context, key_pairs=count + 1)
        except exception.OverQuota:
            raise exception.KeypairLimitExceeded()

    @wrap_exception()
    def import_key_pair(self, context, user_id, key_name, public_key):
        """Import a key pair using an existing public key."""
        self._validate_new_key_pair(context, user_id, key_name)

        self._notify(context, 'import.start', key_name)

        fingerprint = crypto.generate_fingerprint(public_key)

        keypair = objects.KeyPair(context)
        keypair.user_id = user_id
        keypair.name = key_name
        keypair.fingerprint = fingerprint
        keypair.public_key = public_key
        keypair.create()

        self._notify(context, 'import.end', key_name)

        return keypair

    @wrap_exception()
    def create_key_pair(self, context, user_id, key_name):
        """Create a new key pair."""
        self._validate_new_key_pair(context, user_id, key_name)

        self._notify(context, 'create.start', key_name)

        private_key, public_key, fingerprint = crypto.generate_key_pair()

        keypair = objects.KeyPair(context)
        keypair.user_id = user_id
        keypair.name = key_name
        keypair.fingerprint = fingerprint
        keypair.public_key = public_key
        keypair.create()

        self._notify(context, 'create.end', key_name)

        return keypair, private_key

    @wrap_exception()
    def delete_key_pair(self, context, user_id, key_name):
        """Delete a keypair by name."""
        self._notify(context, 'delete.start', key_name)
        objects.KeyPair.destroy_by_name(context, user_id, key_name)
        self._notify(context, 'delete.end', key_name)

    def get_key_pairs(self, context, user_id):
        """List key pairs."""
        return objects.KeyPairList.get_by_user(context, user_id)

    def get_key_pair(self, context, user_id, key_name):
        """Get a keypair by name."""
        return objects.KeyPair.get_by_name(context, user_id, key_name)


class SecurityGroupAPI(base.Base, security_group_base.SecurityGroupBase):
    """Sub-set of the Compute API related to managing security groups
    and security group rules
    """

    # The nova security group api does not use a uuid for the id.
    id_is_uuid = False

    def __init__(self, **kwargs):
        super(SecurityGroupAPI, self).__init__(**kwargs)
        self.security_group_rpcapi = compute_rpcapi.SecurityGroupAPI()

    def validate_property(self, value, property, allowed):
        """Validate given security group property.

        :param value:          the value to validate, as a string or unicode
        :param property:       the property, either 'name' or 'description'
        :param allowed:        the range of characters allowed
        """

        try:
            val = value.strip()
        except AttributeError:
            msg = _("Security group %s is not a string or unicode") % property
            self.raise_invalid_property(msg)
        utils.check_string_length(val, name=property, min_length=1,
                                  max_length=255)

        if allowed and not re.match(allowed, val):
            # Some validation to ensure that values match API spec.
            # - Alphanumeric characters, spaces, dashes, and underscores.
            # TODO(Daviey): LP: #813685 extend beyond group_name checking, and
            #  probably create a param validator that can be used elsewhere.
            msg = (_("Value (%(value)s) for parameter Group%(property)s is "
                     "invalid. Content limited to '%(allowed)s'.") %
                   {'value': value, 'allowed': allowed,
                    'property': property.capitalize()})
            self.raise_invalid_property(msg)

    def ensure_default(self, context):
        """Ensure that a context has a security group.

        Creates a security group for the security context if it does not
        already exist.

        :param context: the security context
        """
        self.db.security_group_ensure_default(context)

    def create_security_group(self, context, name, description):
        try:
            reservations = QUOTAS.reserve(context, security_groups=1)
        except exception.OverQuota:
            msg = _("Quota exceeded, too many security groups.")
            self.raise_over_quota(msg)

        LOG.audit(_("Create Security Group %s"), name, context=context)

        try:
            self.ensure_default(context)

            group = {'user_id': context.user_id,
                     'project_id': context.project_id,
                     'name': name,
                     'description': description}
            try:
                group_ref = self.db.security_group_create(context, group)
            except exception.SecurityGroupExists:
                msg = _('Security group %s already exists') % name
                self.raise_group_already_exists(msg)
            # Commit the reservation
            QUOTAS.commit(context, reservations)
        except Exception:
            with excutils.save_and_reraise_exception():
                QUOTAS.rollback(context, reservations)

        return group_ref

    def update_security_group(self, context, security_group,
                                name, description):
        if security_group['name'] in RO_SECURITY_GROUPS:
            msg = (_("Unable to update system group '%s'") %
                    security_group['name'])
            self.raise_invalid_group(msg)

        group = {'name': name,
                 'description': description}

        columns_to_join = ['rules.grantee_group']
        group_ref = self.db.security_group_update(context,
                security_group['id'],
                group,
                columns_to_join=columns_to_join)
        return group_ref

    def get(self, context, name=None, id=None, map_exception=False):
        self.ensure_default(context)
        try:
            if name:
                return self.db.security_group_get_by_name(context,
                                                          context.project_id,
                                                          name)
            elif id:
                return self.db.security_group_get(context, id)
        except exception.NotFound as exp:
            if map_exception:
                msg = exp.format_message()
                self.raise_not_found(msg)
            else:
                raise

    def list(self, context, names=None, ids=None, project=None,
             search_opts=None):
        self.ensure_default(context)

        groups = []
        if names or ids:
            if names:
                for name in names:
                    groups.append(self.db.security_group_get_by_name(context,
                                                                     project,
                                                                     name))
            if ids:
                for id in ids:
                    groups.append(self.db.security_group_get(context, id))

        elif context.is_admin:
            # TODO(eglynn): support a wider set of search options than just
            # all_tenants, at least include the standard filters defined for
            # the EC2 DescribeSecurityGroups API for the non-admin case also
            if (search_opts and 'all_tenants' in search_opts):
                groups = self.db.security_group_get_all(context)
            else:
                groups = self.db.security_group_get_by_project(context,
                                                               project)

        elif project:
            groups = self.db.security_group_get_by_project(context, project)

        return groups

    def destroy(self, context, security_group):
        if security_group['name'] in RO_SECURITY_GROUPS:
            msg = _("Unable to delete system group '%s'") % \
                    security_group['name']
            self.raise_invalid_group(msg)

        if self.db.security_group_in_use(context, security_group['id']):
            msg = _("Security group is still in use")
            self.raise_invalid_group(msg)

        quotas = objects.Quotas()
        quota_project, quota_user = quotas_obj.ids_from_security_group(
                                context, security_group)
        try:
            quotas.reserve(context, project_id=quota_project,
                           user_id=quota_user, security_groups=-1)
        except Exception:
            LOG.exception(_LE("Failed to update usages deallocating "
                              "security group"))

        LOG.audit(_("Delete security group %s"), security_group['name'],
                  context=context)
        self.db.security_group_destroy(context, security_group['id'])

        # Commit the reservations
        quotas.commit()

    def is_associated_with_server(self, security_group, instance_uuid):
        """Check if the security group is already associated
           with the instance. If Yes, return True.
        """

        if not security_group:
            return False

        instances = security_group.get('instances')
        if not instances:
            return False

        for inst in instances:
            if (instance_uuid == inst['uuid']):
                return True

        return False

    @wrap_check_security_groups_policy
    def add_to_instance(self, context, instance, security_group_name):
        """Add security group to the instance."""
        security_group = self.db.security_group_get_by_name(context,
                context.project_id,
                security_group_name)

        instance_uuid = instance['uuid']

        # check if the security group is associated with the server
        if self.is_associated_with_server(security_group, instance_uuid):
            raise exception.SecurityGroupExistsForInstance(
                                        security_group_id=security_group['id'],
                                        instance_id=instance_uuid)

        self.db.instance_add_security_group(context.elevated(),
                                            instance_uuid,
                                            security_group['id'])
        # NOTE(comstud): No instance_uuid argument to this compute manager
        # call
        self.security_group_rpcapi.refresh_security_group_rules(context,
                security_group['id'], host=instance['host'])

    @wrap_check_security_groups_policy
    def remove_from_instance(self, context, instance, security_group_name):
        """Remove the security group associated with the instance."""
        security_group = self.db.security_group_get_by_name(context,
                context.project_id,
                security_group_name)

        instance_uuid = instance['uuid']

        # check if the security group is associated with the server
        if not self.is_associated_with_server(security_group, instance_uuid):
            raise exception.SecurityGroupNotExistsForInstance(
                                    security_group_id=security_group['id'],
                                    instance_id=instance_uuid)

        self.db.instance_remove_security_group(context.elevated(),
                                               instance_uuid,
                                               security_group['id'])
        # NOTE(comstud): No instance_uuid argument to this compute manager
        # call
        self.security_group_rpcapi.refresh_security_group_rules(context,
                security_group['id'], host=instance['host'])

    def get_rule(self, context, id):
        self.ensure_default(context)
        try:
            return self.db.security_group_rule_get(context, id)
        except exception.NotFound:
            msg = _("Rule (%s) not found") % id
            self.raise_not_found(msg)

    def add_rules(self, context, id, name, vals):
        """Add security group rule(s) to security group.

        Note: the Nova security group API doesn't support adding multiple
        security group rules at once but the EC2 one does. Therefore,
        this function is written to support both.
        """

        count = QUOTAS.count(context, 'security_group_rules', id)
        try:
            projected = count + len(vals)
            QUOTAS.limit_check(context, security_group_rules=projected)
        except exception.OverQuota:
            msg = _("Quota exceeded, too many security group rules.")
            self.raise_over_quota(msg)

        msg = _("Security group %(name)s added %(protocol)s ingress "
                "(%(from_port)s:%(to_port)s)")
        rules = []
        for v in vals:
            rule = self.db.security_group_rule_create(context, v)
            rules.append(rule)
            LOG.audit(msg, {'name': name,
                            'protocol': rule.protocol,
                            'from_port': rule.from_port,
                            'to_port': rule.to_port})

        self.trigger_rules_refresh(context, id=id)
        return rules

    def remove_rules(self, context, security_group, rule_ids):
        msg = _("Security group %(name)s removed %(protocol)s ingress "
                "(%(from_port)s:%(to_port)s)")
        for rule_id in rule_ids:
            rule = self.get_rule(context, rule_id)
            LOG.audit(msg, {'name': security_group['name'],
                            'protocol': rule.protocol,
                            'from_port': rule.from_port,
                            'to_port': rule.to_port})

            self.db.security_group_rule_destroy(context, rule_id)

        # NOTE(vish): we removed some rules, so refresh
        self.trigger_rules_refresh(context, id=security_group['id'])

    def remove_default_rules(self, context, rule_ids):
        for rule_id in rule_ids:
            self.db.security_group_default_rule_destroy(context, rule_id)

    def add_default_rules(self, context, vals):
        rules = [self.db.security_group_default_rule_create(context, v)
                 for v in vals]
        return rules

    def default_rule_exists(self, context, values):
        """Indicates whether the specified rule values are already
           defined in the default security group rules.
        """
        for rule in self.db.security_group_default_rule_list(context):
            keys = ('cidr', 'from_port', 'to_port', 'protocol')
            for key in keys:
                if rule.get(key) != values.get(key):
                    break
            else:
                return rule.get('id') or True
        return False

    def get_all_default_rules(self, context):
        try:
            rules = self.db.security_group_default_rule_list(context)
        except Exception:
            msg = 'cannot get default security group rules'
            raise exception.SecurityGroupDefaultRuleNotFound(msg)

        return rules

    def get_default_rule(self, context, id):
        try:
            return self.db.security_group_default_rule_get(context, id)
        except exception.NotFound:
            msg = _("Rule (%s) not found") % id
            self.raise_not_found(msg)

    def validate_id(self, id):
        try:
            return int(id)
        except ValueError:
            msg = _("Security group id should be integer")
            self.raise_invalid_property(msg)

    def trigger_rules_refresh(self, context, id):
        """Called when a rule is added to or removed from a security_group."""

        security_group = self.db.security_group_get(
            context, id, columns_to_join=['instances'])

        for instance in security_group['instances']:
            if instance['host'] is not None:
                self.security_group_rpcapi.refresh_instance_security_rules(
                        context, instance['host'], instance)

    def trigger_members_refresh(self, context, group_ids):
        """Called when a security group gains a new or loses a member.

        Sends an update request to each compute node for each instance for
        which this is relevant.
        """
        # First, we get the security group rules that reference these groups as
        # the grantee..
        security_group_rules = set()
        for group_id in group_ids:
            security_group_rules.update(
                self.db.security_group_rule_get_by_security_group_grantee(
                                                                     context,
                                                                     group_id))

        # ..then we distill the rules into the groups to which they belong..
        security_groups = set()
        for rule in security_group_rules:
            security_group = self.db.security_group_get(
                context, rule['parent_group_id'],
                columns_to_join=['instances'])
            security_groups.add(security_group)

        # ..then we find the instances that are members of these groups..
        instances = {}
        for security_group in security_groups:
            for instance in security_group['instances']:
                if instance['uuid'] not in instances:
                    instances[instance['uuid']] = instance

        # ..then we send a request to refresh the rules for each instance.
        for instance in instances.values():
            if instance['host']:
                self.security_group_rpcapi.refresh_instance_security_rules(
                        context, instance['host'], instance)

    def get_instance_security_groups(self, context, instance_uuid,
                                     detailed=False):
        if detailed:
            return self.db.security_group_get_by_instance(context,
                                                          instance_uuid)
        instance = objects.Instance(uuid=instance_uuid)
        groups = objects.SecurityGroupList.get_by_instance(context, instance)
        return [{'name': group.name} for group in groups]

    def populate_security_groups(self, instance, security_groups):
        if not security_groups:
            # Make sure it's an empty list and not None
            security_groups = []
        instance.security_groups = security_group_obj.make_secgroup_list(
            security_groups)
