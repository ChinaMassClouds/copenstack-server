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

from horizon import exceptions
from horizon import tables

from openstack_dashboard.api import cinder
from openstack_dashboard.api import keystone

from openstack_dashboard.dashboards.project.volumes.snapshots \
    import tables as snapshots_tables
from openstack_dashboard.dashboards.project.volumes.volumes \
    import tables as volumes_tables
from openstack_dashboard.openstack.common.log import policy_is


class UpdateVolumeSnapshotStatus(tables.LinkAction):
    name = "update_status"
    verbose_name = _("Update Status")
    url = "horizon:admin:volumes:snapshots:update_status"
    classes = ("ajax-modal",)
    icon = "pencil"
    policy_rules = (("volume",
        "snapshot_extension:snapshot_actions:update_snapshot_status"),)


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, snapshot_id):
        snapshot = cinder.volume_snapshot_get(request, snapshot_id)
        snapshot._volume = cinder.volume_get(request, snapshot.volume_id)
        snapshot.host_name = getattr(snapshot._volume,
            'os-vol-host-attr:host')
        tenant_id = getattr(snapshot._volume,
            'os-vol-tenant-attr:tenant_id')
        try:
            tenant = keystone.tenant_get(request, tenant_id)
            snapshot.tenant_name = getattr(tenant, "name")
        except Exception:
            msg = _('Unable to retrieve volume project information.')
            exceptions.handle(request, msg)

        return snapshot


class VolumeSnapshotsTable(volumes_tables.VolumesTableBase):
    name = tables.Column("name", verbose_name=_("Name"),
        link="horizon:admin:volumes:snapshots:detail")
    volume_name = snapshots_tables.SnapshotVolumeNameColumn(
        "name", verbose_name=_("Volume Name"),
        link="horizon:admin:volumes:volumes:detail")
    host = tables.Column("host_name", verbose_name=_("Host"))
    tenant = tables.Column("tenant_name", verbose_name=_("Project"))

    class Meta:
        name = "volume_snapshots"
        verbose_name = _("Volume Snapshots")
        table_actions = (snapshots_tables.DeleteVolumeSnapshot,)
        row_actions = (snapshots_tables.DeleteVolumeSnapshot,
            UpdateVolumeSnapshotStatus,)
        row_class = UpdateRow
        status_columns = ("status",)
        columns = ('tenant', 'host', 'name', 'description', 'size', 'status',
            'volume_name',)

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
