from horizon import messages
from horizon import exceptions
from horizon import tables
from django.template import defaultfilters as filters
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy
from openstack_dashboard import api
from openstack_dashboard.dashboards.admin.controlcenter import constants
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.log import policy_is

class UpdSourceDomainAction(tables.LinkAction):
    name = "update"
    verbose_name = _("Edit Source Domain")
    url = constants.UPDATE_SOURCE_DOMAIN_URL
    classes = ("ajax-modal",)
    icon = "pencil"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')

class AddSourceDomainAction(tables.LinkAction):
    name = "add"
    verbose_name = _("Add Source Domain")
    url = constants.SOURCE_DOMAIN_CREATE_URL
    classes = ("ajax-modal",)
    icon = "plus"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')

class DelSourceDomainAction(tables.DeleteAction):
    @staticmethod
    def action_present(count):
        return ungettext_lazy(
            u"Delete Source Domain",
            u"Delete Source Domains",
            count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Deleted Source Domain",
            u"Deleted Source Domains",
            count
        )

    def delete(self, request, obj_id):
        api.nova.aggregate_delete(request, obj_id)

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')


class AddControlCenterAction(tables.LinkAction):
    name = "add_control_center"
    verbose_name = _("Add Control Center")
    url = "horizon:admin:controlcenter:add_control_center"
    classes = ("ajax-modal",)
    icon = "plus"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')

class DelControlCenterAction(tables.LinkAction):
    name = "del_control_center"
    verbose_name = _("Delete")
    url = constants.CONTROL_CENTER_DELETE_URL
    classes = ("ajax-modal","btn-danger")
    icon = "plus"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')

class HeterogeneousPlatFilterAction(tables.FilterAction):
    def filter(self, table, availability_zones, filter_string):
        q = filter_string.lower()

        def comp(availabilityZone):
            return q in availabilityZone.name.lower()

        return filter(comp, availability_zones)

def get_source_domain_hosts(aggregate):
    return [host for host in aggregate.hosts]

def safe_unordered_list(value):
    return filters.unordered_list(value, autoescape=True)

class ManageHostsAction(tables.LinkAction):
    name = "manage"
    verbose_name = _("Manage Hosts")
    url = constants.SOURCE_DOMAIN_MANAGE_HOSTS_URL
    classes = ("ajax-modal",)
    icon = "plus"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')

class SyncAction(tables.LinkAction):
    name = "sync"
    verbose_name = _("Synchronize")
    url = constants.CONTROL_CENTER_SYNC_URL
    classes = ("ajax-modal",)
    icon = "plus"

    def allowed(self, request, datum):
        return policy_is(request.user.username, 'sysadmin', 'admin', 'syncadmin')

class SourceDomainTable(tables.DataTable):
    name = tables.Column("name", verbose_name=_("Name"))
    availability_zone = tables.Column("availability_zone", verbose_name=_("Availability Zone"))
    hosts = tables.Column(get_source_domain_hosts,
                          verbose_name=_("Hosts"),
                          wrap_list=True,
                          filters=(safe_unordered_list,))
    class Meta:
        name = "source_domain"
        verbose_name = _("Source Domain Info")
        table_actions = (AddSourceDomainAction,
                         DelSourceDomainAction)
        row_actions = (ManageHostsAction,)

    def get_rows(self):
        """Return the row data for this table broken out by columns."""
        rows = []
        policy = policy_is(self.request.user.username, 'sysadmin', 'admin', 'syncadmin')
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
        if not(policy_is(self.request.user.username, 'sysadmin', 'admin', 'syncadmin')):
            self.columns['multi_select'].attrs = {'class':'hide'}
            self.columns['actions'].attrs = {'class':'hide'}
        return self.columns.values()

class HeterogeneousPlatTable(tables.DataTable):
    name = tables.Column("name", verbose_name=_("Name"))
    type = tables.Column("virtualplatformtype", verbose_name=_("Type"))
    ip_addresses = tables.Column("virtualplatformIP", verbose_name=_("IP Addresses"))
    status = tables.Column("status", verbose_name=_("Status"))
    belonged_source_domain = tables.Column("domain_name", verbose_name=_("Belonged Source Domain"))
    data_center_number = tables.Column("datacenternum", verbose_name=_("Data Center Number"))
    clusters_number = tables.Column("clusternum", verbose_name=_("Clusters Number"))

    class Meta:
        name = "heterogeneous_plat"
        verbose_name = _("Heterogeneous Platform")
        table_actions = (HeterogeneousPlatFilterAction,AddControlCenterAction)
        row_actions = (SyncAction,DelControlCenterAction)

    def get_rows(self):
        """Return the row data for this table broken out by columns."""
        rows = []
        policy = policy_is(self.request.user.username, 'sysadmin', 'admin', 'syncadmin')
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
        self.columns['multi_select'].attrs = {'class':'hide'}
        if not(policy_is(self.request.user.username, 'sysadmin', 'admin', 'syncadmin')):
            self.columns['actions'].attrs = {'class':'hide'}
        return self.columns.values()
