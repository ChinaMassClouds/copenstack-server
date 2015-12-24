# Copyright 2012 Nebula, Inc.
#
import logging

from django.http import HttpResponse  # noqa
from django import template
from django.utils.translation import pgettext_lazy
from django.utils.translation import string_concat  # noqa
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy
from horizon import exceptions
from horizon import tables
from horizon.templatetags import sizeformat
from django.core.urlresolvers import reverse_lazy
from openstack_dashboard import api
from django.utils.text import normalize_newlines  # noqa
from openstack_dashboard.models import apply
from openstack_dashboard.openstack.common.log import operate_log
import json
import datetime

LOG = logging.getLogger(__name__)


class LaunchLink(tables.LinkAction):
    name = "launch"
    verbose_name = _("Apply Instance")
    url = "horizon:project:applyhost:launch"
    classes = ("ajax-modal", "btn-launch")
    icon = "cloud-upload"
    ajax = True

    def __init__(self, attrs=None, **kwargs):
        kwargs['preempt'] = True
        super(LaunchLink, self).__init__(attrs, **kwargs)

    def allowed(self, request, datum):
        try:
            limits = api.nova.tenant_absolute_limits(request, reserved=True)

            instances_available = limits['maxTotalInstances'] \
                - limits['totalInstancesUsed']
            cores_available = limits['maxTotalCores'] \
                - limits['totalCoresUsed']
            ram_available = limits['maxTotalRAMSize'] - limits['totalRAMUsed']

            if instances_available <= 0 or cores_available <= 0 \
                    or ram_available <= 0:
                if "disabled" not in self.classes:
                    self.classes = [c for c in self.classes] + ['disabled']
                    self.verbose_name = string_concat(self.verbose_name, ' ',
                                                      _("(Quota exceeded)"))
            else:
                self.verbose_name = _("Apply Instance")
                classes = [c for c in self.classes if c != "disabled"]
                self.classes = classes
        except Exception:
            LOG.exception("Failed to retrieve quota information")
        return True

    def single(self, table, request, object_id=None):
        self.allowed(request, None)
        return HttpResponse(self.render())


def instance_fault_to_friendly_message(instance):
    fault = getattr(instance, 'fault', {})
    message = fault.get('message', _("Unknown"))
    default_message = _("Please try again later [Error: %s].") % message
    fault_map = {
        'NoValidHost': _("There is not enough capacity for this "
                         "flavor in the selected availability zone. "
                         "Try again later or select a different availability "
                         "zone.")
    }
    return fault_map.get(message, default_message)


def get_instance_error(instance):
    if instance.status.lower() != 'error':
        return None
    message = instance_fault_to_friendly_message(instance)
    preamble = _('Failed to launch instance "%s"'
                 ) % instance.name or instance.id
    message = string_concat(preamble, ': ', message)
    return message


class UpdateRow(tables.Row):
    ajax = True


class InstancesFilterAction(tables.FilterAction):
    filter_type = "server"
    filter_choices = (('name', _("Instance Name"), True),
                      ('status', _("Status ="), True),
                      ('image_id', _("Image ID ="), True),
                      ('flavor_id', _("Flavor ID ="), True))


class StartInstance(tables.BatchAction):
    name = "start"
    verbose_name = _("Start")
    success_url = reverse_lazy("horizon:project:instances:index")
    @staticmethod
    def action_present(count):
        return _('Create Instance')

    @staticmethod
    def action_past(count):
        return _('Create Instance')
    
    def allowed(self, request, datum):
        if datum.status=='1':
           return True
        return False

    def action(self, request, obj_id):
        """
        allocate instalce api
        apply create instance
        """
        try:
            if isinstance(obj_id, list):
                res = apply.objects.get(id=obj_id[0])
                p_meta =json.loads( res.meta)
                p_meta['flavor_id'] = res.flavor_id
                if p_meta.get('template_id'):
                    j_flavor_id = '8'
                else:
                    j_flavor_id = res.flavor_id
                api.nova.server_create(request,
                                   res.name,
                                   res.image_id,
                                   j_flavor_id,
                                   res.keypair_id,
                                   normalize_newlines(res.custom_script),
                                   eval(res.security_group_ids),
                                   block_device_mapping=res.dev_mapping_1,
                                   block_device_mapping_v2=res.dev_mapping_2,
                                   nics=eval(res.nics),
                                   availability_zone=res.avail_zone,
                                   instance_count=int(res.count),
                                   admin_pass=res.admin_pass,
                                   disk_config=res.disk_config,
                                   config_drive=res.config_drive,
                                   meta =p_meta)
                apply.objects.filter(id=obj_id[0]).update(status='3')
                operate_log(request.user.username,
                            request.user.roles,
                            res.name+" instances create success")
            else:
                res = apply.objects.get(id=obj_id)
                p_meta =json.loads( res.meta)
                p_meta['flavor_id'] = res.flavor_id
                if p_meta.get('template_id'):
                    j_flavor_id = '8'
                else:
                    j_flavor_id = res.flavor_id
                api.nova.server_create(request,
                                       res.name,
                                       res.image_id,
                                       j_flavor_id,
                                       res.keypair_id,
                                       normalize_newlines(res.custom_script),
                                       eval(res.security_group_ids),
                                       block_device_mapping=res.dev_mapping_1,
                                       block_device_mapping_v2=res.dev_mapping_2,
                                       nics=eval(res.nics),
                                       availability_zone=res.avail_zone,
                                       instance_count=int(res.count),
                                       admin_pass=res.admin_pass,
                                       disk_config=res.disk_config,
                                       config_drive=res.config_drive,
                                       meta =p_meta)
                apply.objects.filter(id=obj_id).update(status='3')
                operate_log(request.user.username,
                            request.user.roles,
                            res.name+" instances create success")
        except Exception:
            if isinstance(obj_id, list):
                apply.objects.filter(id=obj_id[0]).update(status='4')
            else:
                apply.objects.filter(id=obj_id).update(status='4')
            operate_log(request.user.username,
                        request.user.roles,
                        res.name+" instances create error")
            exceptions.handle(request, _('Error in creating'))


class DropInstance(tables.DeleteAction):
    name = "drop"
    verbose_name = _("Drop")
    @staticmethod
    def action_present(count):
        return _('Deleted Apply Instance')

    @staticmethod
    def action_past(count):
        return _('Deleted Apply Instance')

    def delete(self, request, obj_id):
        """
        apply delete
        """
        apply_instances = apply.objects.filter(id=obj_id)
        apply_instances.update(status='5')
        operate_log(request.user.username,
                    request.user.roles,
                    apply_instances[0].name+" instances drop")


def get_size(instance):
    if hasattr(instance, "full_flavor"):
        template_name = 'project/applyhost/_instance_flavor.html'
        size_ram = sizeformat.mb_float_format(instance.full_flavor.ram)
        if instance.full_flavor.disk > 0:
            size_disk = sizeformat.diskgbformat(instance.full_flavor.disk)
        else:
            size_disk = _("%s GB") % "0"
        context = {
            "name": instance.full_flavor.name,
            "id": instance.id,
            "size_disk": size_disk,
            "size_ram": size_ram,
            "vcpus": instance.full_flavor.vcpus
        }
        return template.loader.render_to_string(template_name, context)
    return _("Not available")


#apply status
APPLY_DISPLAY_CHOICES = (
    ("0", pgettext_lazy("Apply state of an Instance", _("Pending approval"))),
    ("1", pgettext_lazy("Apply state of an Instance", _("Approved"))),
    ("2", pgettext_lazy("Apply state of an Instance", _("Refuse"))),
    ("3", pgettext_lazy("Apply state of an Instance", _("Create Success"))),
    ("4", pgettext_lazy("Apply state of an Instance", _("Create Error"))),
)

APPLY_DISPLAY_CHOICES_TRANSLATE = (
    ("0",  "Pending approval"),
    ("1",  "Approved"),
    ("2",  "Refuse"),
    ("3",  "Create Success"),
    ("4",  "Create Error"),
)


class InstancesTable(tables.DataTable):
    name = tables.Column("name",
#                          link=("horizon:project:applyhost:detail"),
                         verbose_name=_("Instance Name"))
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    image_name = tables.Column("image_name",
                               verbose_name=_("Image Name"))
    count = tables.Column("count",
                          verbose_name=_("Count"))
    reason = tables.Column("info",
                           verbose_name=_("Reason"))
    create_date = tables.Column("create_date",
                                verbose_name=_("Create Date"),
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),),
                                attrs={'data-type': 'timesince'})
    status = tables.Column("status",
                           verbose_name=_("Status"),
                           display_choices=APPLY_DISPLAY_CHOICES)

    class Meta:
        name = "instances"
        verbose_name = _("Apply Instance List")
        row_class = UpdateRow
        table_actions = (LaunchLink,
                         InstancesFilterAction,
                         DropInstance
                        )
        row_actions = (StartInstance,DropInstance,)
