# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from django.utils.translation import ugettext_lazy as _

from horizon import tables
from openstack_dashboard.dashboards.project.volumes \
    .volumes import tables as volumes_tables
from openstack_dashboard.openstack.common.log import policy_is


class VolumesFilterAction(tables.FilterAction):

    def filter(self, table, volumes, filter_string):
        """Naive case-insensitive search."""
        q = filter_string.lower()
        return [volume for volume in volumes
                if q in volume.name.lower()]


class UpdateVolumeStatusAction(tables.LinkAction):
    name = "update_status"
    verbose_name = _("Update Volume Status")
    url = "horizon:admin:volumes:volumes:update_status"
    classes = ("ajax-modal",)
    icon = "pencil"
    policy_rules = (("volume",
        "volume_extension:volume_admin_actions:reset_status"),)


class VolumesTable(volumes_tables.VolumesTable):
    name = tables.Column("name",
                         verbose_name=_("Name"),
                         link="horizon:admin:volumes:volumes:detail")
    host = tables.Column("os-vol-host-attr:host", verbose_name=_("Host"))
    tenant = tables.Column("tenant_name", verbose_name=_("Project"))

    class Meta:
        name = "volumes"
        verbose_name = _("Volumes")
        status_columns = ["status"]
        row_class = volumes_tables.UpdateRow
        table_actions = (volumes_tables.DeleteVolume, VolumesFilterAction)
        row_actions = (volumes_tables.DeleteVolume, UpdateVolumeStatusAction)
        columns = ('tenant', 'host', 'name', 'size', 'status', 'volume_type',
                   'attachments', 'bootable', 'encryption',)

    def get_rows(self):
        """Return the row data for this table broken out by columns."""
        rows = []
        policy = policy_is(self.request.user.username, 'sysadmin', 'admin')
        for datum in self.filtered_data:
            row = self._meta.row_class(self, datum)
            if self.get_object_id(datum) == self.current_item_id:
                self.selected = True
                row.classes.append('current_selected')
            if not policy:
                del row.cells['actions']
                del row.cells['multi_select']
            rows.append(row)
        return rows

    def get_columns(self):
       if not(policy_is(self.request.user.username, 'sysadmin', 'admin')):
           self.columns['multi_select'].attrs = {'class':'hide'}
           self.columns['actions'].attrs = {'class':'hide'}
       return self.columns.values()
