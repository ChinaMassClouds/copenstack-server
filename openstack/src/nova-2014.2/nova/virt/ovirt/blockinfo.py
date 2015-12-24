# Copyright (C) 2012-2013 Red Hat, Inc.
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

"""
Handling of block device information and mapping.

This module contains helper methods for interpreting the block
device information and determining the suitable mapping to
guest devices and libvirt XML.

Throughout these methods there are a number of standard
variables / types used

 * 'mapping': a dict contains the storage device mapping.

   For the default disk types it will contain the following
   keys & values:

      'disk' -> disk_info
      'disk.rescue' -> disk_info
      'disk.local' -> disk_info
      'disk.swap' -> disk_info
      'disk.config' -> disk_info

   If any of the default disks are overridden by the block
   device info mappings, the hash value will be None

   For any ephemeral device there will also be a dict entry

      'disk.eph$NUM' -> disk_info

   For any volume device there will also be a dict entry:

       $path -> disk_info

   Finally a special key will refer to the root device:

      'root' -> disk_info


 * 'disk_info': a tuple specifying disk configuration

   It contains the following 3 fields

      (disk bus, disk dev, device type)

   and possibly these optional fields: ('format',)

 * 'disk_bus': the guest bus type ('ide', 'virtio', 'scsi', etc)

 * 'disk_dev': the device name 'vda', 'hdc', 'sdf', 'xvde' etc

 * 'device_type': type of device eg 'disk', 'cdrom', 'floppy'

 * 'format': Which format to apply to the device if applicable

 * 'boot_index': Number designating the boot order of the device

"""

import itertools
import operator

from oslo.config import cfg

from nova import block_device
from nova.compute import arch
from nova.compute import flavors
from nova import exception
from nova.i18n import _
from nova.objects import base as obj_base
from nova.virt import block_device as driver_block_device
from nova.virt import configdrive
from nova.virt import driver
from nova.virt.libvirt import utils as libvirt_utils

CONF = cfg.CONF


SUPPORTED_DEVICE_TYPES = ('disk', 'cdrom', 'floppy', 'lun')
BOOT_DEV_FOR_TYPE = {'disk': 'hd', 'cdrom': 'cdrom', 'floppy': 'fd'}


def has_disk_dev(mapping, disk_dev):
    """Determine if a disk device name has already been used.

       Looks at all the keys in mapping to see if any
       corresponding disk_info tuple has a device name
       matching disk_dev

       Returns True if the disk_dev is in use.
    """

    for disk in mapping:
        info = mapping[disk]
        if info['dev'] == disk_dev:
            return True
    return False


def get_dev_prefix_for_disk_bus(disk_bus):
    """Determine the dev prefix for a disk bus.

       Determine the dev prefix to be combined
       with a disk number to fix a disk_dev.
       eg 'hd' for 'ide' bus can be used to
       form a disk dev 'hda'

       Returns the dev prefix or raises an
       exception if the disk bus is unknown.
    """

    if CONF.libvirt.disk_prefix:
        return CONF.libvirt.disk_prefix
    if disk_bus == "ide":
        return "hd"
    elif disk_bus == "virtio":
        return "vd"
    elif disk_bus == "xen":
        # Two possible mappings for Xen, xvda or sda
        # which are interchangeable, so we pick sda
        return "sd"
    elif disk_bus == "scsi":
        return "sd"
    elif disk_bus == "usb":
        return "sd"
    elif disk_bus == "fdc":
        return "fd"
    elif disk_bus == "uml":
        return "ubd"
    elif disk_bus == "lxc":
        return None
    else:
        raise exception.NovaException(
            _("Unable to determine disk prefix for %s") %
            disk_bus)


def get_dev_count_for_disk_bus(disk_bus):
    """Determine the number disks supported.

       Determine how many disks can be supported in
       a single VM for a particular disk bus.

       Returns the number of disks supported.
    """

    if disk_bus == "ide":
        return 4
    else:
        return 26


def find_disk_dev_for_disk_bus(mapping, bus, last_device=False):
    """Identify a free disk dev name for a bus.

       Determines the possible disk dev names for
       the bus, and then checks them in order until
       it identifies one that is not yet used in the
       disk mapping. If 'last_device' is set, it will
       only consider the last available disk dev name.

       Returns the chosen disk_dev name, or raises an
       exception if none is available.
    """

    dev_prefix = get_dev_prefix_for_disk_bus(bus)
    if dev_prefix is None:
        return None

    max_dev = get_dev_count_for_disk_bus(bus)
    if last_device:
        devs = [max_dev - 1]
    else:
        devs = range(max_dev)

    for idx in devs:
        disk_dev = dev_prefix + chr(ord('a') + idx)
        if not has_disk_dev(mapping, disk_dev):
            return disk_dev

    raise exception.NovaException(
        _("No free disk device names for prefix '%s'"),
        dev_prefix)


def is_disk_bus_valid_for_virt(virt_type, disk_bus):
    valid_bus = {
        'qemu': ['virtio', 'scsi', 'ide', 'usb', 'fdc'],
        'kvm': ['virtio', 'scsi', 'ide', 'usb', 'fdc'],
        'xen': ['xen', 'ide'],
        'uml': ['uml'],
        'lxc': ['lxc'],
        }

    if virt_type not in valid_bus:
        raise exception.UnsupportedVirtType(virt=virt_type)

    return disk_bus in valid_bus[virt_type]


def get_disk_bus_for_device_type(virt_type,
                                 image_meta=None,
                                 device_type="disk"):
    """Determine the best disk bus to use for a device type.

       Considering the currently configured virtualization
       type, return the optimal disk_bus to use for a given
       device type. For example, for a disk on KVM it will
       return 'virtio', while for a CDROM it will return 'ide'
       on x86_64 and 'scsi' on ppc64.

       Returns the disk_bus, or returns None if the device
       type is not supported for this virtualization
    """

    # Prefer a disk bus set against the image first of all
    if image_meta:
        key = "hw_" + device_type + "_bus"
        disk_bus = image_meta.get('properties', {}).get(key)
        if disk_bus is not None:
            if not is_disk_bus_valid_for_virt(virt_type, disk_bus):
                raise exception.UnsupportedHardware(model=disk_bus,
                                                    virt=virt_type)
            return disk_bus

    # Otherwise pick a hypervisor default disk bus
    if virt_type == "uml":
        if device_type == "disk":
            return "uml"
    elif virt_type == "lxc":
        return "lxc"
    elif virt_type == "xen":
        if device_type == "cdrom":
            return "ide"
        elif device_type == "disk":
            return "xen"
    elif virt_type in ("qemu", "kvm"):
        if device_type == "cdrom":
            guestarch = libvirt_utils.get_arch(image_meta)
            if guestarch in (arch.PPC, arch.PPC64):
                return "scsi"
            else:
                return "ide"
        elif device_type == "disk":
            return "virtio"
        elif device_type == "floppy":
            return "fdc"

    return None


def get_disk_bus_for_disk_dev(virt_type, disk_dev):
    """Determine the disk bus for a disk device.

       Given a disk device like 'hda', 'sdf', 'xvdb', etc
       guess what the most appropriate disk bus is for
       the currently configured virtualization technology

       Returns the disk bus, or raises an Exception if
       the disk device prefix is unknown.
    """

    if disk_dev[:2] == 'hd':
        return "ide"
    elif disk_dev[:2] == 'sd':
        # Reverse mapping 'sd' is not reliable
        # there are many possible mappings. So
        # this picks the most likely mappings
        if virt_type == "xen":
            return "xen"
        else:
            return "scsi"
    elif disk_dev[:2] == 'vd':
        return "virtio"
    elif disk_dev[:2] == 'fd':
        return "fdc"
    elif disk_dev[:3] == 'xvd':
        return "xen"
    elif disk_dev[:3] == 'ubd':
        return "uml"
    else:
        raise exception.NovaException(
            _("Unable to determine disk bus for '%s'") %
            disk_dev[:1])


def get_next_disk_info(mapping, disk_bus,
                       device_type='disk',
                       last_device=False,
                       boot_index=None):
    """Determine the disk info for the next device on disk_bus.

       Considering the disks already listed in the disk mapping,
       determine the next available disk dev that can be assigned
       for the disk bus.

       Returns the disk_info for the next available disk.
    """

    disk_dev = find_disk_dev_for_disk_bus(mapping,
                                          disk_bus,
                                          last_device)
    info = {'bus': disk_bus,
            'dev': disk_dev,
            'type': device_type}

    if boot_index is not None and boot_index >= 0:
        info['boot_index'] = str(boot_index)

    return info


def get_eph_disk(index):
    return 'disk.eph' + str(index)


def get_config_drive_type():
    """Determine the type of config drive.

       If config_drive_format is set to iso9660 then the config drive will
       be 'cdrom', otherwise 'disk'.

       Returns a string indicating the config drive type.
    """

    if CONF.config_drive_format == 'iso9660':
        config_drive_type = 'cdrom'
    elif CONF.config_drive_format == 'vfat':
        config_drive_type = 'disk'
    else:
        raise exception.ConfigDriveUnknownFormat(
            format=CONF.config_drive_format)

    return config_drive_type


def get_info_from_bdm(virt_type, bdm, mapping=None, disk_bus=None,
                      dev_type=None, allowed_types=None,
                      assigned_devices=None):
    mapping = mapping or {}
    allowed_types = allowed_types or SUPPORTED_DEVICE_TYPES
    device_name = block_device.strip_dev(get_device_name(bdm))

    bdm_type = bdm.get('device_type') or dev_type
    if bdm_type not in allowed_types:
        bdm_type = 'disk'

    bdm_bus = bdm.get('disk_bus') or disk_bus
    if not is_disk_bus_valid_for_virt(virt_type, bdm_bus):
        if device_name:
            bdm_bus = get_disk_bus_for_disk_dev(virt_type, device_name)
        else:
            bdm_bus = get_disk_bus_for_device_type(virt_type, None, bdm_type)

    if not device_name:
        if assigned_devices:
            padded_mapping = dict((dev, {'dev': dev})
                for dev in assigned_devices)
            padded_mapping.update(mapping)
        else:
            padded_mapping = mapping

        device_name = find_disk_dev_for_disk_bus(padded_mapping, bdm_bus)

    bdm_info = {'bus': bdm_bus,
                'dev': device_name,
                'type': bdm_type}

    bdm_format = bdm.get('guest_format')
    if bdm_format:
        bdm_info.update({'format': bdm_format})

    boot_index = bdm.get('boot_index')
    if boot_index is not None and boot_index >= 0:
        # NOTE(ndipanov): libvirt starts ordering from 1, not 0
        bdm_info['boot_index'] = str(boot_index + 1)

    return bdm_info


def get_device_name(bdm):
    """Get the device name if present regardless of the bdm format."""
    if isinstance(bdm, obj_base.NovaObject):
        return bdm.device_name
    else:
        return bdm.get('device_name') or bdm.get('mount_device')


def get_root_info(virt_type, image_meta, root_bdm, disk_bus, cdrom_bus,
                  root_device_name=None):

    # NOTE (ndipanov): This is a hack to avoid considering an image
    #                  BDM with local target, as we don't support them
    #                  yet. Only applies when passed non-driver format
    no_root_bdm = (not root_bdm or (
        root_bdm.get('source_type') == 'image' and
        root_bdm.get('destination_type') == 'local'))
    if no_root_bdm:
        if (image_meta and image_meta.get('disk_format') == 'iso'):
            root_device_bus = cdrom_bus
            root_device_type = 'cdrom'
        else:
            root_device_bus = disk_bus
            root_device_type = 'disk'
        if root_device_name:
            root_device_bus = get_disk_bus_for_disk_dev(virt_type,
                                                        root_device_name)
        else:
            root_device_name = find_disk_dev_for_disk_bus({}, root_device_bus)

        return {'bus': root_device_bus,
                'type': root_device_type,
                'dev': block_device.strip_dev(root_device_name),
                'boot_index': '1'}
    else:
        if not get_device_name(root_bdm) and root_device_name:
            root_bdm = root_bdm.copy()
            root_bdm['device_name'] = root_device_name
        return get_info_from_bdm(virt_type, root_bdm, {}, disk_bus)


def default_device_names(virt_type, context, instance, root_device_name,
                         ephemerals, swap, block_device_mapping):

    block_device_info = {
        'root_device_name': root_device_name,
        'swap': driver_block_device.get_swap(
            driver_block_device.convert_swap(swap)),
        'ephemerals': driver_block_device.convert_ephemerals(ephemerals),
        'block_device_mapping': (
            driver_block_device.convert_volumes(
                block_device_mapping) +
            driver_block_device.convert_snapshots(
                block_device_mapping) +
            driver_block_device.convert_blanks(
                block_device_mapping))
    }

    get_disk_info(virt_type, instance, block_device_info)

    for driver_bdm in itertools.chain(block_device_info['ephemerals'],
                               [block_device_info['swap']] if
                               block_device_info['swap'] else [],
                               block_device_info['block_device_mapping']):
        driver_bdm.save(context)


def has_default_ephemeral(instance, disk_bus, block_device_info, mapping):
    ephemerals = driver.block_device_info_get_ephemerals(block_device_info)
    if instance['ephemeral_gb'] <= 0 or ephemerals:
        return None
    else:
        info = get_next_disk_info(mapping, disk_bus)
        if block_device.volume_in_mapping(info['dev'], block_device_info):
            return None
        return info


def update_bdm(bdm, info):
    device_name_field = ('device_name'
                         if 'device_name' in bdm
                         else 'mount_device')
    # Do not update the device name if it was already present
    bdm.update(dict(zip((device_name_field,
                         'disk_bus', 'device_type'),
                        ((bdm.get(device_name_field) or
                          block_device.prepend_dev(info['dev'])),
                         info['bus'], info['type']))))


def get_disk_mapping(virt_type, instance,
                     disk_bus, cdrom_bus,
                     block_device_info=None,
                     image_meta=None, rescue=False):
    """Determine how to map default disks to the virtual machine.

       This is about figuring out whether the default 'disk',
       'disk.local', 'disk.swap' and 'disk.config' images have
       been overridden by the block device mapping.

       Returns the guest disk mapping for the devices.
    """

    inst_type = flavors.extract_flavor(instance)

    mapping = {}

    pre_assigned_device_names = \
    [block_device.strip_dev(get_device_name(bdm)) for bdm in itertools.chain(
        driver.block_device_info_get_ephemerals(block_device_info),
        [driver.block_device_info_get_swap(block_device_info)],
        driver.block_device_info_get_mapping(block_device_info))
     if get_device_name(bdm)]

    if rescue:
        rescue_info = get_next_disk_info(mapping,
                                         disk_bus, boot_index=1)
        mapping['disk.rescue'] = rescue_info
        mapping['root'] = rescue_info

        os_info = get_next_disk_info(mapping,
                                     disk_bus)
        mapping['disk'] = os_info

        return mapping

    # NOTE (ndipanov): root_bdm can be None when we boot from image
    # as there is no driver represenation of local targeted images
    # and they will not be in block_device_info list.
    root_bdm = block_device.get_root_bdm(
        driver.block_device_info_get_mapping(block_device_info))

    root_device_name = block_device.strip_dev(
        driver.block_device_info_get_root(block_device_info))
    root_info = get_root_info(virt_type, image_meta, root_bdm,
                              disk_bus, cdrom_bus, root_device_name)

    mapping['root'] = root_info
    # NOTE (ndipanov): This implicitly relies on image->local BDMs not
    #                  being considered in the driver layer - so missing
    #                  bdm with boot_index 0 means - use image, unless it was
    #                  overridden. This can happen when using legacy syntax and
    #                  no root_device_name is set on the instance.
    if not root_bdm and not block_device.volume_in_mapping(root_info['dev'],
                                                           block_device_info):
        mapping['disk'] = root_info

    default_eph = has_default_ephemeral(instance, disk_bus, block_device_info,
                                        mapping)
    if default_eph:
        mapping['disk.local'] = default_eph

    for idx, eph in enumerate(driver.block_device_info_get_ephemerals(
            block_device_info)):
        eph_info = get_info_from_bdm(
            virt_type, eph, mapping, disk_bus,
            assigned_devices=pre_assigned_device_names)
        mapping[get_eph_disk(idx)] = eph_info
        update_bdm(eph, eph_info)

    swap = driver.block_device_info_get_swap(block_device_info)
    if swap and swap.get('swap_size', 0) > 0:
        swap_info = get_info_from_bdm(virt_type, swap, mapping, disk_bus)
        mapping['disk.swap'] = swap_info
        update_bdm(swap, swap_info)
    elif inst_type['swap'] > 0:
        swap_info = get_next_disk_info(mapping,
                                       disk_bus)
        if not block_device.volume_in_mapping(swap_info['dev'],
                                              block_device_info):
            mapping['disk.swap'] = swap_info

    block_device_mapping = driver.block_device_info_get_mapping(
        block_device_info)

    for vol in block_device_mapping:
        vol_info = get_info_from_bdm(
            virt_type, vol, mapping,
            assigned_devices=pre_assigned_device_names)
        mapping[block_device.prepend_dev(vol_info['dev'])] = vol_info
        update_bdm(vol, vol_info)

    if configdrive.required_by(instance):
        device_type = get_config_drive_type()
        disk_bus = get_disk_bus_for_device_type(virt_type,
                                                image_meta,
                                                device_type)
        config_info = get_next_disk_info(mapping,
                                         disk_bus,
                                         device_type,
                                         last_device=True)
        mapping['disk.config'] = config_info

    return mapping


def get_disk_info(virt_type, instance, block_device_info=None,
                  image_meta=None, rescue=False):
    """Determine guest disk mapping info.

       This is a wrapper around get_disk_mapping, which
       also returns the chosen disk_bus and cdrom_bus.
       The returned data is in a dict

            - disk_bus: the bus for harddisks
            - cdrom_bus: the bus for CDROMs
            - mapping: the disk mapping

       Returns the disk mapping disk.
    """

    disk_bus = get_disk_bus_for_device_type(virt_type, image_meta, "disk")
    cdrom_bus = get_disk_bus_for_device_type(virt_type, image_meta, "cdrom")
    mapping = get_disk_mapping(virt_type, instance,
                               disk_bus, cdrom_bus,
                               block_device_info,
                               image_meta, rescue)

    return {'disk_bus': disk_bus,
            'cdrom_bus': cdrom_bus,
            'mapping': mapping}


def get_boot_order(disk_info):
    boot_mapping = (info for name, info in disk_info['mapping'].iteritems()
                    if name != 'root' and info.get('boot_index') is not None)
    boot_devs_dup = (BOOT_DEV_FOR_TYPE[dev['type']] for dev in
                     sorted(boot_mapping,
                            key=operator.itemgetter('boot_index')))

    def uniq(lst):
        s = set()
        return [el for el in lst if el not in s and not s.add(el)]

    return uniq(boot_devs_dup)
