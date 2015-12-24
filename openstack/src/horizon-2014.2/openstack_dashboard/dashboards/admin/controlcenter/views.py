from horizon import tables
from horizon import workflows
from horizon import forms
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _
from openstack_dashboard.dashboards.admin.controlcenter \
    import constants
from openstack_dashboard.dashboards.admin.controlcenter \
    import tables as controlcenter_tables
from openstack_dashboard.dashboards.admin.controlcenter \
    import workflows as controlcenter_workflows
from openstack_dashboard.dashboards.admin.controlcenter \
    import forms as controlcenter_forms
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from openstack_dashboard.openstack.common.base import f_getIpByHostname
from openstack_dashboard import api
from django.core.urlresolvers import reverse_lazy
import json
import logging
from django import http
from horizon import messages

LOG = logging.getLogger(__name__)

def get_heterogeneous_plat(request):
    plats = []
    err_msg = 'Unable to retrieve heterogeneous platforms list.'
    try:
        request_api = RequestApi()
        plats = request_api.getRequestInfo('api/heterogeneous/platforms')

        if plats == None or type(plats) != type([]):
            messages.error(request,_(err_msg))
            return []
        
        plats.sort(key=lambda aggregate: aggregate['name'].lower())
        res = DictList2ObjectList(plats,'uuid')
        return res
    except Exception:
        exceptions.handle(request,_(err_msg))
    return []

_get_heterogeneous_plat = get_heterogeneous_plat

class ManageHostsView(workflows.WorkflowView):
    template_name = constants.SOURCE_DOMAIN_MANAGE_HOSTS_TEMPLATE
    workflow_class = controlcenter_workflows.ManageSourceDomainHostsWorkflow
    success_url = reverse_lazy(constants.SOURCE_DOMAIN_INDEX_URL)

    def get_initial(self):
        return {'id': self.kwargs["id"]}

    def get_context_data(self, **kwargs):
        context = super(ManageHostsView, self).get_context_data(**kwargs)
        context['id'] = self.kwargs['id']
        return context
    
class IndexView(tables.MultiTableView):
    template_name = 'admin/controlcenter/index.html'
    table_classes = (controlcenter_tables.SourceDomainTable,
                     controlcenter_tables.HeterogeneousPlatTable)
    
    def get_source_domain_data(self):
        request = self.request
        aggregates = []
        try:
            aggregates = api.nova.aggregate_details_list(self.request)
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve source domains list.'))
        aggregates.sort(key=lambda aggregate: aggregate.name.lower())
        return aggregates
    
    def get_heterogeneous_plat_data(self):
        return get_heterogeneous_plat(self.request)
        

class SourceDomainUpdateView(forms.ModalFormView):
    template_name = constants.SOURCE_DOMAIN_UPDATE_VIEW_TEMPLATE
    form_class = controlcenter_forms.UpdateSourceDomainInfoForm
    success_url = reverse_lazy(constants.SOURCE_DOMAIN_INDEX_URL)

    def get_initial(self):
        aggregate = self.get_object()
        return {'id': self.kwargs["id"],
                'name': aggregate.name,
                'availability_zone': aggregate.availability_zone}

    def get_context_data(self, **kwargs):
        context = super(SourceDomainUpdateView, self).get_context_data(**kwargs)
        context['id'] = self.kwargs['id']
        return context

    def get_object(self):
        if not hasattr(self, "_object"):
            aggregate_id = self.kwargs['id']
            try:
                self._object = \
                    api.nova.aggregate_get(self.request, aggregate_id)
            except Exception:
                msg = _('Unable to retrieve the aggregate to be updated')
                exceptions.handle(self.request, msg)
        return self._object

class SourceDomainCreateView(workflows.WorkflowView):
    workflow_class = controlcenter_workflows.AddSourceDomainWorkflow
    template_name = constants.SOURCE_DOMAIN_CREATE_VIEW_TEMPLATE
    
class ControlCenterCreateView(workflows.WorkflowView):
    workflow_class = controlcenter_workflows.AddControlCenterWorkflow
    
class ControlCenterCreateView2(workflows.WorkflowView):
    workflow_class = controlcenter_workflows.AddControlCenterWorkflow2
    template_name = constants.CONTROL_CENTER_CREATE_VIEW_TEMPLATE2

class ControlCenterSyncView(forms.ModalFormView):
    template_name = constants.CONTROL_CENTER_SYNC_VIEW_TEMPLATE
    form_class = controlcenter_forms.SyncControlCenterForm
    success_url = reverse_lazy(constants.SOURCE_DOMAIN_INDEX_URL)

    def get_initial(self):
        plat_info = get_plat_info(self.request,self.kwargs['id'])
        return {'tenantname': self.request.user.project_name,
                'username': self.request.user,
                'passwd': '',
                'domain_name': plat_info.get('domain_name'),
                'hostname': plat_info.get('hostname'),
                'virtualplatformtype': plat_info.get('virtualplatformtype'),
                'virtualplatformIP':plat_info.get('virtualplatformIP'),
                'virtualplatformusername':plat_info.get('virtualplatformusername'),
                'name':plat_info.get('name'),
                'datacentersandclusters':json.dumps(plat_info.get('dc_cluster')),
                'network_id': ''}

    def get_context_data(self, **kwargs):
        context = super(ControlCenterSyncView, self).get_context_data(**kwargs)
        context['id'] = self.kwargs['id']
        return context

def get_plat_info(request,plat_id):
    if plat_id:
        try:
            request_api = RequestApi()
            plat_info_list = request_api.getRequestInfo('api/heterogeneous/platforms/%s' % plat_id) or []
            for plat in plat_info_list:
                if plat :
                    return plat
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve heterogeneous platforms info.'))
    return {}
    
class ControlCenterDeleteView(forms.ModalFormView):
    template_name = constants.CONTROL_CENTER_DELETE_VIEW_TEMPLATE
    form_class = controlcenter_forms.DeleteControlCenterForm
    success_url = reverse_lazy(constants.SOURCE_DOMAIN_INDEX_URL)

    def get_initial(self):
        plat_id = self.kwargs['id']
        plat_info = get_plat_info(self.request, plat_id)
        return {'tenantname': self.request.user.project_name,
                'username': self.request.user,
                'passwd': '',
                'hostname': self.get_host_name(),
                'virtualplatformtype': plat_info.get('virtualplatformtype'),
                'name':plat_info.get('name'),
                'id': plat_id}

    def get_context_data(self, **kwargs):
        context = super(ControlCenterDeleteView, self).get_context_data(**kwargs)
        context['id'] = self.kwargs['id']
        return context

    def get_host_name(self):
        plat_id = ''
        if not hasattr(self, "_object"):
            plat_id = self.kwargs['id']

        if plat_id:
            try:
                request_api = RequestApi()
                plat_info_list = request_api.getRequestInfo('api/heterogeneous/platforms/%s' % plat_id) or []

                for plat in plat_info_list:
                    if plat and plat.get('hostname'):
                        return plat.get('hostname')
            except Exception:
                exceptions.handle(request,
                                  _('Unable to retrieve heterogeneous platforms info.'))
        return ''
    
def domain_hosts(request,domain_id):
    hosts = query_hosts_by_domain(request,domain_id)
    res = [h.get('address') for h in hosts]
    return http.HttpResponse(json.dumps(res))

def domain_vms(request,domain_id):
    instances = []
    try:
        domain_info = api.nova.aggregate_get(request, str(domain_id))
        if domain_info :
            vms = None
            try:
                vms, _more = api.nova.server_list(request, all_tenants=True)
            except Exception:
                exceptions.handle(request,_('Unable to retrieve instance list.'))
            if vms and type(vms) == type([]):
                for v in vms:
                    if getattr(v,'OS-EXT-AZ:availability_zone','') == getattr(domain_info,'availability_zone',''):
                        instances.append({'id':getattr(v,'id',''),'name':getattr(v,'name','')})
    except Exception:
        exceptions.handle(request,_('Unable to retrieve vms list.'))

    return http.HttpResponse(json.dumps(instances))

def query_hosts_by_domain(request,domain_id):
    hosts = []
    domain_info = None
    try:
        domain_info = api.nova.aggregate_get(request, domain_id)
        for h in getattr(domain_info,'hosts'):
            ip = f_getIpByHostname(h)
            hosts.append({'name':ip,'address':ip})
    except Exception:
        msg = _('Unable to retrieve the aggregate to be updated')
        exceptions.handle(request, msg)
        
    try:
        request_api = RequestApi()
        hosts2 = request_api.getRequestInfo('api/heterogeneous/platforms/hosts')
        if type(hosts2) != type([]):
            messages.error(request,
                          _('Unable to retrieve hosts list.'))
            hosts2 = []
    except Exception:
        hosts2 = []
        exceptions.handle(request,
                          _('Unable to retrieve hosts list.'))
    
    if hosts2 and domain_info:
        hosts += [{'name':h.get('name'),'address':h.get('address')} for h in hosts2 
                  if h.get('domain') == domain_info.availability_zone]

    return hosts

