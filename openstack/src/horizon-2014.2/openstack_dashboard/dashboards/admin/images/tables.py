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

from django.utils.translation import ugettext_lazy as _

from horizon import tables

from openstack_dashboard import api
from openstack_dashboard.dashboards.project.images.images \
    import tables as project_tables
from openstack_dashboard.openstack.common.log import policy_is


class AdminCreateImage(project_tables.CreateImage):
    url = "horizon:admin:images:create"

    def allowed(self, request, image=None):
        return policy_is(request.user.username, 'admin', 'sysadmin')


class AdminDeleteImage(project_tables.DeleteImage):

    def allowed(self, request, image=None):
        if image and image.protected:
            return False
        else:
            return policy_is(request.user.username, 'admin', 'sysadmin')


class AdminEditImage(project_tables.EditImage):
    url = "horizon:admin:images:update"

    def allowed(self, request, image=None):
        return True


class UpdateMetadata(tables.LinkAction):
    url = "horizon:admin:images:update_metadata"
    name = "update_metadata"
    verbose_name = _("Update Metadata")
    classes = ("ajax-modal",)
    icon = "pencil"


class UpdateRow(tables.Row):
    ajax = True

    def get_data(self, request, image_id):
        image = api.glance.image_get(request, image_id)
        return image


class AdminImageFilterAction(tables.FilterAction):
    filter_type = "server"
    filter_choices = (('name', _("Image Name ="), True),
                      ('status', _('Status ='), True),
                      ('disk_format', _('Format ='), True),
                      ('size_min', _('Min. Size (MB)'), True),
                      ('size_max', _('Max. Size (MB)'), True))


class AdminImagesTable(project_tables.ImagesTable):
    name = tables.Column("name",
                         link="horizon:admin:images:detail",
                         verbose_name=_("Image Name"))

    class Meta:
        name = "images"
        row_class = UpdateRow
        status_columns = ["status"]
        verbose_name = _("Images")
        table_actions = (AdminCreateImage, AdminDeleteImage,
                         AdminImageFilterAction)
        row_actions = (AdminEditImage, UpdateMetadata, AdminDeleteImage)


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
