# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
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

from django.core.urlresolvers import reverse
from django.template import defaultfilters as filters
from django.utils.http import urlencode
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

from horizon import tables

from openstack_dashboard import api
from openstack_dashboard.openstack.common.log import policy_is


class DeleteFlavor(tables.DeleteAction):
    @staticmethod
    def action_present(count):
        return ungettext_lazy(
            u"Delete Flavor",
            u"Delete Flavors",
            count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Deleted Flavor",
            u"Deleted Flavors",
            count
        )

    def delete(self, request, obj_id):
        api.nova.flavor_delete(request, obj_id)

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'admin', 'sysadmin')


class CreateFlavor(tables.LinkAction):
    name = "create"
    verbose_name = _("Create Flavor")
    url = "horizon:admin:flavors:create"
    classes = ("ajax-modal",)
    icon = "plus"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'admin', 'sysadmin')


class UpdateFlavor(tables.LinkAction):
    name = "update"
    verbose_name = _("Edit Flavor")
    url = "horizon:admin:flavors:update"
    classes = ("ajax-modal",)
    icon = "pencil"


class UpdateMetadata(tables.LinkAction):
    url = "horizon:admin:flavors:update_metadata"
    name = "update_metadata"
    verbose_name = _("Update Metadata")
    classes = ("ajax-modal",)
    icon = "pencil"


class ModifyAccess(tables.LinkAction):
    name = "projects"
    verbose_name = _("Modify Access")
    url = "horizon:admin:flavors:update"
    classes = ("ajax-modal",)
    icon = "pencil"

    def get_link_url(self, flavor):
        step = 'update_flavor_access'
        base_url = reverse(self.url, args=[flavor.id])
        param = urlencode({"step": step})
        return "?".join([base_url, param])


class FlavorFilterAction(tables.FilterAction):
    def filter(self, table, flavors, filter_string):
        """Really naive case-insensitive search."""
        q = filter_string.lower()

        def comp(flavor):
            return q in flavor.name.lower()

        return filter(comp, flavors)


def get_size(flavor):
    return _("%sMB") % flavor.ram


def get_swap_size(flavor):
    return _("%sMB") % (flavor.swap or 0)


def get_disk_size(flavor):
    return _("%sGB") % (flavor.disk or 0)


def get_ephemeral_size(flavor):
    return _("%sGB") % getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral', 0)


def get_extra_specs(flavor):
    return flavor.get_keys()


class FlavorsTable(tables.DataTable):
    name = tables.Column('name', verbose_name=_('Flavor Name'))
    vcpus = tables.Column('vcpus', verbose_name=_('VCPUs'))
    ram = tables.Column(get_size,
                        verbose_name=_('RAM'),
                        attrs={'data-type': 'size'})
    disk = tables.Column(get_disk_size,
                         verbose_name=_('Root Disk'),
                         attrs={'data-type': 'size'})
    ephemeral = tables.Column(get_ephemeral_size,
                              verbose_name=_('Ephemeral Disk'),
                              attrs={'data-type': 'size'})
    swap = tables.Column(get_swap_size,
                         verbose_name=_('Swap Disk'),
                         attrs={'data-type': 'size'})
    flavor_id = tables.Column('id', verbose_name=_('ID'))
    public = tables.Column("is_public",
                           verbose_name=_("Public"),
                           empty_value=False,
                           filters=(filters.yesno, filters.capfirst))
    extra_specs = tables.Column(get_extra_specs,
                                verbose_name=_("Metadata"),
                                link="horizon:admin:flavors:update_metadata",
                                link_classes=("ajax-modal",),
                                empty_value=False,
                                filters=(filters.yesno, filters.capfirst))

    class Meta:
        name = "flavors"
        verbose_name = _("Flavors")
        table_actions = (FlavorFilterAction, CreateFlavor, DeleteFlavor)
        row_actions = (UpdateFlavor,
                       ModifyAccess,
                       UpdateMetadata,
                       DeleteFlavor)

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
