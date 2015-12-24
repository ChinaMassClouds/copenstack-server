# Copyright 2012 Nebula, Inc.
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

from django.utils.translation import pgettext_lazy
from django.core.urlresolvers import NoReverseMatch  # noqa
from django.core.urlresolvers import reverse
from django.http import HttpResponse  # noqa
from django.template import defaultfilters as filters
from django.utils import html
from django.utils.http import urlencode
from django.utils import safestring
from django.utils.translation import string_concat  # noqa
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

from horizon import exceptions
from horizon import tables

from openstack_dashboard import api
from openstack_dashboard.api import cinder
from openstack_dashboard import policy
from openstack_dashboard.openstack.common.log import policy_is
from django.core.urlresolvers import reverse_lazy
from openstack_dashboard.openstack.common.log import operate_log
from openstack_dashboard.models import applydisk
import datetime

DELETABLE_STATES = ("available", "error", "error_extending")


class VolumePolicyTargetMixin(policy.PolicyTargetMixin):
    policy_target_attrs = (("project_id", 'os-vol-tenant-attr:tenant_id'),)


class LaunchVolume(tables.LinkAction):
    name = "launch_volume"
    verbose_name = _("Launch as Disk")
    url = "horizon:project:instances:launch"
    classes = ("ajax-modal", "btn-launch")
    icon = "cloud-upload"

    def allowed(self, request, volume=None):
        if getattr(volume, 'bootable', '') == 'true':
            return volume.status == "available"
        return False

class StartVolume(tables.BatchAction):
    name = "start"
    verbose_name = _("Start")
    success_url = reverse_lazy("horizon:project:volumes:index")

    @staticmethod
    def action_present(count):
        return ungettext_lazy(
            u"Create Disk",
            u"Create Disk",
            count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Create Disk",
            u"Create Disk",
            count
        )
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
                res = applydisk.objects.get(id=obj_id[0])
                cinder.volume_create(request,
                                   res.size,
                                   res.name,
                                   res.description,
                                   res.type,
                                   snapshot_id=res.snapshot_id,
                                   availability_zone=res.az,
                                   image_id=res.image_id,
                                   metadata=eval(res.metadata),
                                   source_volid=res.volume_id)
                applydisk.objects.filter(id=obj_id[0]).update(status='3')
                operate_log(request.user.username,
                            request.user.roles,
                            res.name+" disk create success")
            else:
                res = applydisk.objects.get(id=obj_id)
                cinder.volume_create(request,
                                     res.size,
                                     res.name,
                                     res.description,
                                     res.type,
                                     snapshot_id=res.snapshot_id,
                                     availability_zone=res.az,
                                     image_id=res.image_id,
                                     metadata=eval(res.metadata),
                                     source_volid=res.volume_id)
                applydisk.objects.filter(id=obj_id[0]).update(status='3')
                operate_log(request.user.username,
                            request.user.roles,
                            res.name+" disk create success")
        except Exception:
            if isinstance(obj_id, list):
                applydisk.objects.filter(id=obj_id[0]).update(status='4')
            else:
                applydisk.objects.filter(id=obj_id).update(status='4')
            operate_log(request.user.username,
                        request.user.roles,
                        res.name+" disk create error")
            exceptions.handle(request, _('Error in creating'))


class DeleteVolume(VolumePolicyTargetMixin, tables.DeleteAction):
    @staticmethod
    def action_present(count):
        return _('Deleted Apply Disk')

    @staticmethod
    def action_past(count):
        return _('Deleted Apply Disk')


    def delete(self, request, obj_id):
        obj = self.table.get_object_by_id(obj_id)
        name = self.table.get_object_display(obj)
        try:
            apply = applydisk.objects.filter(id=obj_id)
            apply.update(status='5')
        except Exception:
            msg = _('Unable to delete volume "%s". One or more snapshots '
                    'depend on it.')
            exceptions.check_message(["snapshots", "dependent"], msg % name)
            raise



class CreateVolume(tables.LinkAction):
    name = "create"
    verbose_name = _("Apply Volume")
    url = "horizon:project:applydisk:create"
    classes = ("ajax-modal",)
    icon = "plus"
    ajax = True

    def __init__(self, attrs=None, **kwargs):
        kwargs['preempt'] = True
        super(CreateVolume, self).__init__(attrs, **kwargs)

    def allowed(self, request, volume=None):
        limits = api.cinder.tenant_absolute_limits(request)

        gb_available = (limits.get('maxTotalVolumeGigabytes', float("inf"))
                        - limits.get('totalGigabytesUsed', 0))
        volumes_available = (limits.get('maxTotalVolumes', float("inf"))
                             - limits.get('totalVolumesUsed', 0))

        if gb_available <= 0 or volumes_available <= 0:
            if "disabled" not in self.classes:
                self.classes = [c for c in self.classes] + ['disabled']
                self.verbose_name = string_concat(self.verbose_name, ' ',
                                                  _("(Quota exceeded)"))
        else:
            self.verbose_name = _("Apply Volume")
            classes = [c for c in self.classes if c != "disabled"]
            self.classes = classes
        return True

    def single(self, table, request, object_id=None):
        self.allowed(request, None)
        return HttpResponse(self.render())



class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, volume_id):
        volume = cinder.volume_get(request, volume_id)
        return volume


def get_size(volume):
    return _("%sGB") % volume.size






def get_volume_type(volume):
    return volume.volume_type if volume.volume_type != "None" else None


def get_encrypted_value(volume):
    if not hasattr(volume, 'encrypted') or volume.encrypted is None:
        return "-"
    elif volume.encrypted is False:
        return _("No")
    else:
        return _("Yes")

class VolumesFilterAction(tables.FilterAction):

    def filter(self, table, volumes, filter_string):
        """Naive case-insensitive search."""
        q = filter_string.lower()
        return [volume for volume in volumes
                if q in volume.name.lower()]

#apply status
APPLY_DISPLAY_CHOICES = (
    ("0", pgettext_lazy("Apply state of an Disk", _("Pending approval"))),
    ("1", pgettext_lazy("Apply state of an Disk", _("Approved"))),
    ("2", pgettext_lazy("Apply state of an Disk", _("Refuse"))),
    ("3", pgettext_lazy("Apply state of an Disk", _("Create Success"))),
    ("4", pgettext_lazy("Apply state of an Disk", _("Create Error"))),
)

class VolumesTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"))
    description = tables.Column("description",
                                verbose_name=_("Description"),
                                truncate=40)
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    volume_type = tables.Column("type",
                                verbose_name=_("Type"),
                                empty_value="-")
    availability_zone = tables.Column("az",
                         verbose_name=_("Availability Zone"))
    create_date = tables.Column("create_date",
                                verbose_name=_("Create Date"),
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),),
                                attrs={'data-type': 'timesince'})
    status = tables.Column("status",
                           verbose_name=_("Status"),
                           display_choices=APPLY_DISPLAY_CHOICES)

    class Meta:
        name = "volumes"
        verbose_name = _("Volumes")
        row_class = UpdateRow
        table_actions = (CreateVolume, DeleteVolume, VolumesFilterAction)
        row_actions = (StartVolume,
                       DeleteVolume)

