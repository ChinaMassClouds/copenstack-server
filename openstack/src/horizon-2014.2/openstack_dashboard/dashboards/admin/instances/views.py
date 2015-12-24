# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 OpenStack Foundation
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
from django.core.urlresolvers import reverse_lazy
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext_lazy as _
from horizon import exceptions
from horizon import forms
from horizon import tables
from horizon.utils import memoized
from openstack_dashboard.openstack.common import choices
from openstack_dashboard import api
from openstack_dashboard.dashboards.admin.instances \
    import forms as project_forms
from openstack_dashboard.dashboards.admin.instances \
    import tables as project_tables
from openstack_dashboard.dashboards.project.instances import views
from openstack_dashboard.dashboards.project.applyhost.workflows \
    import update_instance

from openstack_dashboard.dashboards.admin.controlcenter import views as controlcenter_views
from openstack_dashboard.openstack.common.requestapi import RequestApi,def_vcenter_vms,def_cserver_vms
import logging

LOG = logging.getLogger(__name__)

# re-use console from project.instances.views to make reflection work
def console(args, **kvargs):
    return views.console(args, **kvargs)


# re-use vnc from project.instances.views to make reflection work
def vnc(args, **kvargs):
    return views.vnc(args, **kvargs)


# re-use spice from project.instances.views to make reflection work
def spice(args, **kvargs):
    return views.spice(args, **kvargs)


# re-use rdp from project.instances.views to make reflection work
def rdp(args, **kvargs):
    return views.rdp(args, **kvargs)


class AdminUpdateView(views.UpdateView):
    workflow_class = update_instance.AdminUpdateInstance


class AdminIndexView(tables.DataTableView):
    table_class = project_tables.AdminInstancesTable
    template_name = 'admin/instances/index.html'

    def has_more_data(self, table):
        return self._more

    def has_prev_data(self, table):
        return self._prev
    
    def get_vcenter_uuid_maps_info(self):
        try:
            request_api = RequestApi()
            uuid_maps = request_api.getRequestInfo('api/heterogeneous/platforms/vcenter/uuid_maps') or []
            return uuid_maps
        except Exception:
            return {}

    def get_cserver_uuid_maps_info(self):
        try:
            request_api = RequestApi()
            uuid_maps = request_api.getRequestInfo('api/heterogeneous/platforms/cserver/uuid_maps') or []
            return uuid_maps
        except Exception:
            return {}

    def get_heterogeneous_plat(self, request):
        zarr = []
        heterogeneous_plat = controlcenter_views.get_heterogeneous_plat(request)
        for i in heterogeneous_plat:
            zarr.append((i.domain_name,i.virtualplatformtype,i.name))
        return zarr

    def get_data(self):
        instances = []
        marker = self.request.GET.get(
            project_tables.AdminInstancesTable._meta.pagination_param, None)
        prev_marker = self.request.GET.get(
            project_tables.AdminInstancesTable._meta.prev_pagination_param, None)
        search_opts = self.get_filters({'marker': marker,'prev_marker': prev_marker, 'paginate': True})
        try:
            instances, self._more, self._prev = api.nova.server_list_with_prev(
                self.request,
                search_opts=search_opts,
                all_tenants=True)

        except Exception:
            self._more = False
            exceptions.handle(self.request,
                              _('Unable to retrieve instance list.'))

        if instances:
            vcenter_uuid_maps_info = self.get_vcenter_uuid_maps_info()
            cserver_uuid_maps_info = self.get_cserver_uuid_maps_info()
            try:
                api.network.servers_update_addresses(self.request, instances,
                                                     all_tenants=True)
            except Exception:
                exceptions.handle(
                    self.request,
                    message=_('Unable to retrieve IP addresses from Neutron.'),
                    ignore=True)

            # Gather our flavors to correlate against IDs
            try:
                flavors = api.nova.flavor_list(self.request)
            except Exception:
                # If fails to retrieve flavor list, creates an empty list.
                flavors = []

            # Gather our tenants to correlate against IDs
            try:
                tenants, has_more = api.keystone.tenant_list(self.request)
            except Exception:
                tenants = []
                msg = _('Unable to retrieve instance project information.')
                exceptions.handle(self.request, msg)

            full_flavors = SortedDict([(f.id, f) for f in flavors])
            tenant_dict = SortedDict([(t.id, t) for t in tenants])
            
            # zhangdebo
            zarr = []
            zarr_got = False
            vcenter_vms = []
            cserver_vms = []
            vcenter_vms_got = False
            cserver_vms_got = False
            
            # Loop through instances to get flavor and tenant info.
            for inst in instances:
                inst.virtualplatformtype = 'Openstack'
#                 for i in zarr:
#                     if i[0] == getattr(inst,'OS-EXT-AZ:availability_zone',''):
                if inst.metadata and inst.metadata.get('platformtype'):
                    inst.virtualplatformtype = inst.metadata.get('platformtype')
                    if inst.virtualplatformtype == 'vcenter':
                        setattr(inst,'OS-EXT-SRV-ATTR:host','-')
                        if not vcenter_vms_got:
                            if not zarr_got:
                                zarr = self.get_heterogeneous_plat(self.request)
                                zarr_got = True
                            for i in zarr:
                                if i[0] == getattr(inst,'OS-EXT-AZ:availability_zone',''):
                                    vcenter_vms += def_vcenter_vms(i[2])
                                    vcenter_vms_got = True
                                    break
                        for v in vcenter_vms:
                            if v.get('id') == inst.id:
                                setattr(inst,'OS-EXT-SRV-ATTR:host',v.get('host'))
                                break
                    elif inst.virtualplatformtype == 'cserver':
                        setattr(inst,'OS-EXT-SRV-ATTR:host','-')
                        if not cserver_vms_got:
                            if not zarr_got:
                                zarr = self.get_heterogeneous_plat(self.request)
                                zarr_got = True
                            for i in zarr:
                                if i[0] == getattr(inst,'OS-EXT-AZ:availability_zone',''):
                                    cserver_vms += def_cserver_vms(i[2])
                                    cserver_vms_got = True
                        for v in cserver_vms:
                            if v.get('openstack_uuid') == inst.id:
                                setattr(inst,'OS-EXT-SRV-ATTR:host',v.get('hostname'))
                                break
#                         break

                if getattr(inst,'virtualplatformtype','') == 'vcenter':
                    if vcenter_uuid_maps_info.get(inst.id):
                        flavor_id = vcenter_uuid_maps_info.get(inst.id).get('flavor_id') or inst.flavor["id"]
                        for i in inst.addresses.keys():
                            for j in inst.addresses[i]:
                                j['addr'] = vcenter_uuid_maps_info.get(inst.id).get('ip') or ''
                    else:
                        flavor_id = inst.flavor["id"]
                        for i in inst.addresses.keys():
                            for j in inst.addresses[i]:
                                j['addr'] = ''
                elif getattr(inst,'virtualplatformtype','') == 'cserver':
                    if cserver_uuid_maps_info.get(inst.id):
                        flavor_id = cserver_uuid_maps_info.get(inst.id).get('flavor_id') or ''
                        for i in inst.addresses.keys():
                            for j in inst.addresses[i]:
                                j['addr'] = cserver_uuid_maps_info.get(inst.id).get('ip') or ''
                    else:
                        flavor_id = ''
                        for i in inst.addresses.keys():
                            for j in inst.addresses[i]:
                                j['addr'] = ''
                else:
                    flavor_id = inst.flavor["id"]
                    
                if getattr(inst,'virtualplatformtype',''):
                    inst.virtualplatformtype = choices.translate(choices.CHOICES_VIRTUAL_TYPE,inst.virtualplatformtype) 
                    
                try:
                    if flavor_id in full_flavors:
                        inst.full_flavor = full_flavors[flavor_id]
                    else:
                        # If the flavor_id is not in full_flavors list,
                        # gets it via nova api.
                        inst.full_flavor = api.nova.flavor_get(
                            self.request, flavor_id)
                except Exception:
                    pass
#                     msg = _('Unable to retrieve instance size information.')
#                     exceptions.handle(self.request, msg)
                tenant = tenant_dict.get(inst.tenant_id, None)
                inst.tenant_name = getattr(tenant, "name", None)
        return instances

    def get_filters(self, filters):
        filter_field = self.table.get_filter_field()
        filter_action = self.table._meta._filter_action
        if filter_action.is_api_filter(filter_field):
            filter_string = self.table.get_filter_string()
            if filter_field and filter_string:
                filters[filter_field] = filter_string
        return filters


class LiveMigrateView(forms.ModalFormView):
    form_class = project_forms.LiveMigrateForm
    template_name = 'admin/instances/live_migrate.html'
    context_object_name = 'instance'
    success_url = reverse_lazy("horizon:admin:instances:index")

    def get_context_data(self, **kwargs):
        context = super(LiveMigrateView, self).get_context_data(**kwargs)
        context["instance_id"] = self.kwargs['instance_id']
        return context

    @memoized.memoized_method
    def get_hosts(self, *args, **kwargs):
        try:
            return api.nova.host_list(self.request)
        except Exception:
            redirect = reverse("horizon:admin:instances:index")
            msg = _('Unable to retrieve host information.')
            exceptions.handle(self.request, msg, redirect=redirect)

    @memoized.memoized_method
    def get_object(self, *args, **kwargs):
        instance_id = self.kwargs['instance_id']
        try:
            return api.nova.server_get(self.request, instance_id)
        except Exception:
            redirect = reverse("horizon:admin:instances:index")
            msg = _('Unable to retrieve instance details.')
            exceptions.handle(self.request, msg, redirect=redirect)

    def get_initial(self):
        initial = super(LiveMigrateView, self).get_initial()
        _object = self.get_object()
        if _object:
            current_host = getattr(_object, 'OS-EXT-SRV-ATTR:host', '')
            initial.update({'instance_id': self.kwargs['instance_id'],
                            'current_host': current_host,
                            'hosts': self.get_hosts()})
        return initial


class DetailView(views.DetailView):
    redirect_url = 'horizon:admin:instances:index'
