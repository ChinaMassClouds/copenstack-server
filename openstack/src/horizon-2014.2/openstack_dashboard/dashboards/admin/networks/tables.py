# Copyright 2012 NEC Corporation
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

import logging

from django.core.urlresolvers import reverse
from django.template import defaultfilters as filters
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

from horizon import exceptions
from horizon import tables

from openstack_dashboard import api
from openstack_dashboard.dashboards.project.networks \
    import tables as project_tables
from openstack_dashboard import policy
from openstack_dashboard.openstack.common.log import policy_is

LOG = logging.getLogger(__name__)


class DeleteNetwork(policy.PolicyTargetMixin, tables.DeleteAction):
    @staticmethod
    def action_present(count):
        return ungettext_lazy(
            u"Delete Network",
            u"Delete Networks",
            count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Deleted Network",
            u"Deleted Networks",
            count
        )

    policy_rules = (("network", "delete_network"),)

    def delete(self, request, obj_id):
        try:
            api.neutron.network_delete(request, obj_id)
        except Exception:
            msg = _('Failed to delete network %s') % obj_id
            LOG.info(msg)
            redirect = reverse('horizon:admin:networks:index')
            exceptions.handle(request, msg, redirect=redirect)

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin')


class CreateNetwork(tables.LinkAction):
    name = "create"
    verbose_name = _("Create Network")
    url = "horizon:admin:networks:create"
    classes = ("ajax-modal",)
    icon = "plus"
    policy_rules = (("network", "create_network"),)
    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin')

class EditNetwork(policy.PolicyTargetMixin, tables.LinkAction):
    name = "update"
    verbose_name = _("Edit Network")
    url = "horizon:admin:networks:update"
    classes = ("ajax-modal",)
    icon = "pencil"
    policy_rules = (("network", "update_network"),)


# def _get_subnets(network):
#    cidrs = [subnet.get('cidr') for subnet in network.subnets]
#    return ','.join(cidrs)


class NetworksTable(tables.DataTable):
    tenant = tables.Column("tenant_name", verbose_name=_("Project"))
    name = tables.Column("name", verbose_name=_("Network Name"),
                         link='horizon:admin:networks:detail')
    subnets = tables.Column(project_tables.get_subnets,
                            verbose_name=_("Subnets Associated"),)
    num_agents = tables.Column("num_agents",
                               verbose_name=_("DHCP Agents"))
    shared = tables.Column("shared", verbose_name=_("Shared"),
                           filters=(filters.yesno, filters.capfirst))
    status = tables.Column("status", verbose_name=_("Status"))
    admin_state = tables.Column("admin_state",
                                verbose_name=_("Admin State"))

    class Meta:
        name = "networks"
        verbose_name = _("Networks")
        table_actions = (CreateNetwork, DeleteNetwork)
        row_actions = (EditNetwork, DeleteNetwork)

    def __init__(self, request, data=None, needs_form_wrapper=None, **kwargs):
        super(NetworksTable, self).__init__(request, data=data,
                                        needs_form_wrapper=needs_form_wrapper,
                                        **kwargs)
        if not api.neutron.is_extension_supported(request,
                                                  'dhcp_agent_scheduler'):
            del self.columns['num_agents']

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
