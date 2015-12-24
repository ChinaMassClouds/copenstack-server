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

import json

from django.utils.translation import ugettext_lazy as _

from horizon import messages
from horizon import exceptions
from horizon import forms
from horizon import workflows

from openstack_dashboard import api
from openstack_dashboard.openstack.common import choices
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from openstack_dashboard.dashboards.admin.controlcenter import constants
from openstack_dashboard.openstack.common.log import operate_log
    
class GlobalVars:
    avilible_clusters = []
    control_center_info = {}

class SetSourceDomainInfoAction(workflows.Action):
    name = forms.CharField(label=_("Name"),
                           max_length=255)

    availability_zone = forms.CharField(label=_("Availability Zone"),
                                        max_length=255)
#     exists_source_domain = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        name = _("Source Domain Info")
        help_text = _("Source domain divide an availability zone into "
                      "logical units by grouping together hosts. Create a "
                      "source domain then select the hosts contained in it.")
        slug = "set_source_domain_info"
        
    def __init__(self, request, *args, **kwargs):
        super(SetSourceDomainInfoAction, self).__init__(request, *args, **kwargs)
        
    def clean(self):
        cleaned_data = super(SetSourceDomainInfoAction, self).clean()
        name = cleaned_data.get('name')
        availability_zone = cleaned_data.get('availability_zone')

        try:
            aggregates = api.nova.aggregate_details_list(self.request)
        except Exception:
            msg = _('Unable to get source domain list')
            exceptions.check_message(["Connection", "refused"], msg)
            raise
        if aggregates is not None:
            for aggregate in aggregates:
                if aggregate.name.lower() == name.lower():
                    raise forms.ValidationError(
                        _('The name "%s" is already used by '
                          'another source domain.')
                        % name
                    )
                if aggregate.availability_zone.lower() == availability_zone.lower():
                    raise forms.ValidationError(
                        _('The availability_zone "%s" is already used by '
                          'another source domain.')
                        % availability_zone
                    )
        return cleaned_data
    
class SetControlCenterInfoAction(workflows.Action):
    name = forms.CharField(max_length=100, label=_("Name"))
    domain_name = forms.ChoiceField(label=_("Belonged Source Domain"),
                                    help_text=_('Only those domains that have only one child-host can be used.'))
    hostname = forms.ChoiceField(label=_("Host"))
    virtualplatformtype = forms.ChoiceField(label=_("Type"),choices=choices.CHOICES_VIRTUAL_TYPE)
    network_id = forms.ChoiceField(label=_("Network Name"))
    tenantname = forms.CharField(label=_("Tenant Name"),required=False,
                                 widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    username = forms.CharField(label=_("Cloud Platform Account"),required=False,
                                 widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    passwd = forms.CharField(label=_("Cloud Platform Password"),
                                              widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))
    virtualplatformIP = forms.IPAddressField(max_length=255, label=_("Heterogeneous Platform IP Address"))
    virtualplatformusername = forms.CharField(max_length=50, label=_("Heterogeneous Platform Account"))
    virtualplatformpassword = forms.CharField(label=_("Heterogeneous Platform Password"),
                                              widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))
    all_hosts = forms.CharField(widget=forms.HiddenInput)
    
    class Meta:
        name = _("Control Center Info")
        help_text = _("Please fill in the information of control center.")
        slug = "set_control_center_info"
        
    def __init__(self, request, *args, **kwargs):
        super(SetControlCenterInfoAction, self).__init__(request, *args, **kwargs)
        aggregates = []
        try:
            aggregates = api.nova.aggregate_details_list(self.request)
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve source domains list.'))
        domain_names = []
        hosts_dic = {}
        avilible_hosts = []
        
        occupied = self.get_occupied()
        
        for agg in aggregates:
            hosts = agg.hosts
            hosts_dic[str(agg.availability_zone)] = []
            empty_domain = True

            if hosts and len(hosts) == 1:
                for h in hosts:
                    if h not in occupied.get('occupied_hostname'):
                        hosts_dic[str(agg.availability_zone)].append(h)
                        avilible_hosts.append((str(h),str(h)))
                        empty_domain = False
                if not empty_domain:
                    domain_names.append((agg.availability_zone,agg.availability_zone))

        self.fields['domain_name'].choices = domain_names
        self.fields['all_hosts'].initial = json.dumps(hosts_dic)
        self.fields['hostname'].choices = avilible_hosts
        self.fields['tenantname'].initial = request.user.project_name
        self.fields['username'].initial = request.user
        
        networks = []
        try:
            _networks = api.neutron.network_list(self.request)
            networks = [(n.id,n.name) for n in _networks]
        except Exception:
            networks = []
            msg = _('Network list can not be retrieved.')
            exceptions.handle(request, msg)
        self.fields['network_id'].choices = networks

    def clean(self):
        cleaned_data = super(SetControlCenterInfoAction, self).clean()
        name = cleaned_data.get('name')
        occupied = self.get_occupied()
        occupied_name = occupied.get('occupied_name')
        if name in occupied_name:
            raise forms.ValidationError(
                        _('The name "%s" is already used by '
                          'another control center.')
                        % name
                    )
        virtualplatformIP = cleaned_data.get('virtualplatformIP')
        if virtualplatformIP in occupied.get('occupied_virtualplatformIP'):
            raise forms.ValidationError(
                        _('The virtualplatformIP "%s" has already taken over by another domain.')
                        % virtualplatformIP
                    )
        GlobalVars.control_center_info = cleaned_data
        return cleaned_data
    
    def get_occupied(self):
        err_msg = 'Unable to retrieve heterogeneous platforms list.'
        res = {'occupied_hostname':[],'occupied_name':[],'occupied_virtualplatformIP':[]}
        try:
            request_api = RequestApi()
            plats = request_api.getRequestInfo('api/heterogeneous/platforms')

            if plats and type(plats) == type([]):
                res['occupied_hostname'] = [p.get('hostname') for p in plats]
                res['occupied_name'] = [p.get('name') for p in plats]
                res['occupied_virtualplatformIP'] = [p.get('virtualplatformIP') for p in plats]
        except Exception:
            exceptions.handle(self.request,_(err_msg))
        return res

class SetSourceDomainInfoStep(workflows.Step):
    action_class = SetSourceDomainInfoAction
    contributes = ("name","availability_zone")
    


class AddHostsToSourceDomainAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(AddHostsToSourceDomainAction, self).__init__(request,
                                                        *args,
                                                        **kwargs)
        err_msg = _('Unable to get the available hosts')

        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)

        hosts = []
        try:
            hosts = api.nova.host_list(request)
        except Exception:
            exceptions.handle(request, err_msg)

        host_names = []
        for host in hosts:
            if host.host_name not in host_names and host.service == u'compute':
                host_names.append(host.host_name)
        host_names.sort()

        self.fields[field_name].choices = \
            [(host_name, host_name) for host_name in host_names]

    class Meta:
        name = _("Manage Hosts within Source Domain")
        slug = "add_host_to_source_domain"

class AddClustersToControlCenterAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(AddClustersToControlCenterAction, self).__init__(request,
                                                        *args,
                                                        **kwargs)
        err_msg = _('Unable to get the available hosts')
        
        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)
        self.fields[field_name].choices = GlobalVars.avilible_clusters

    class Meta:
        name = _("Manage Clusters within Control Center")
        slug = "add_clusters_to_control_center"
        

        
class AddHostsToSourceDomainStep(workflows.UpdateMembersStep):
    action_class = AddHostsToSourceDomainAction
    help_text = _("Add hosts to this source domain. Hosts can be in multiple "
                  "source domains.")
    available_list_title = _("All available hosts")
    members_list_title = _("Selected hosts")
    no_available_text = _("No hosts found.")
    no_members_text = _("No host selected.")
    show_roles = False
    contributes = ("hosts_aggregate",)

    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['hosts_aggregate'] = data.get(member_field_name, [])
        return context
    
class AddClustersToControlCenterStep(workflows.UpdateMembersStep):
    action_class = AddClustersToControlCenterAction
    help_text = _("Add clusters to this control center. Clusters can be in multiple control centers.")
    available_list_title = _("All available clusters")
    members_list_title = _("Selected clusters")
    no_available_text = _("No clusters found.")
    no_members_text = _("No clusters selected.")
    show_roles = False
    contributes = ("datacentersandclusters",)

    def contribute(self, data, context):
        context = GlobalVars.control_center_info
        if data:
            member_field_name = self.get_member_field_name('member')
            res = {}
            clusters_list = data.get(member_field_name, [])
            for c in clusters_list:
                datacenter = c[c.rindex('(') + 2:c.rindex(')') - 1]
                if not res.get(datacenter):
                    res[datacenter] = [c[:c.rindex('(') - 1]]
                else:
                    res[datacenter].append(c[:c.rindex('(') - 1])
            context['datacentersandclusters'] = res
        return context

class ManageSourceDomainHostsAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(ManageSourceDomainHostsAction, self).__init__(request,
                                                         *args,
                                                         **kwargs)
        err_msg = _('Unable to get the available hosts')

        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)

        aggregate_id = self.initial['id']
        aggregate = api.nova.aggregate_get(request, aggregate_id)
        current_aggregate_hosts = aggregate.hosts

        hosts = []
        try:
            hosts = api.nova.host_list(request)
        except Exception:
            exceptions.handle(request, err_msg)

        host_names = []
        for host in hosts:
            if host.host_name not in host_names and host.service == u'compute':
                host_names.append(host.host_name)
        host_names.sort()

        self.fields[field_name].choices = \
            [(host_name, host_name) for host_name in host_names]

        self.fields[field_name].initial = current_aggregate_hosts

    class Meta:
        name = _("Manage Hosts within Source Domain")

class ManageSourceDomainHostsStep(workflows.UpdateMembersStep):
    action_class = ManageSourceDomainHostsAction
    help_text = _("Add hosts to this source domain or remove hosts from it. "
                  "Hosts can be in multiple source domains.")
    available_list_title = _("All Available Hosts")
    members_list_title = _("Selected Hosts")
    no_available_text = _("No Hosts found.")
    no_members_text = _("No Host selected.")
    show_roles = False
    depends_on = ("id",)
    contributes = ("hosts_aggregate",)

    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['hosts_aggregate'] = data.get(member_field_name, [])
        return context
    
class ManageSourceDomainHostsWorkflow(workflows.Workflow):
    slug = "manage_hosts_source_domain"
    name = _("Add/Remove Hosts to Source Domain")
    finalize_button_name = _("Save")
    success_message = _('The source domain was updated.')
    failure_message = _('Unable to update the source domain.')
    success_url = constants.SOURCE_DOMAIN_INDEX_URL
    default_steps = (ManageSourceDomainHostsStep, )

    def handle(self, request, context):
        aggregate_id = context['id']
        aggregate = api.nova.aggregate_get(request, aggregate_id)
        current_aggregate_hosts = set(aggregate.hosts)
        context_hosts_aggregate = set(context['hosts_aggregate'])
        removed_hosts = current_aggregate_hosts - context_hosts_aggregate
        added_hosts = context_hosts_aggregate - current_aggregate_hosts
        try:
            for host in removed_hosts:
                api.nova.remove_host_from_aggregate(request,
                                                    aggregate_id,
                                                    host)
            for host in added_hosts:
                api.nova.add_host_to_aggregate(request, aggregate_id, host)
        except Exception:
            exceptions.handle(
                request, _('Error when adding or removing hosts.'))
            return False
        return True
        
class AddSourceDomainWorkflow(workflows.Workflow):
    slug = "add_source_domain"
    name = _("Add Source Domain")
    finalize_button_name = _("Add Source Domain")
    success_message = _('Added new source domain "%s".')
    failure_message = _('Unable to add source domain "%s".')
    success_url = constants.SOURCE_DOMAIN_INDEX_URL
    default_steps = (SetSourceDomainInfoStep, AddHostsToSourceDomainStep)

    def handle(self, request, context):
        try:
            self.object = \
                api.nova.aggregate_create(
                    request,
                    name=context['name'],
                    availability_zone=context['availability_zone'])
            operate_log(request.user.username,
                        request.user.roles,
                        context["name"] + "aggragate create")

        except Exception:
            exceptions.handle(request, _('Unable to create source domain.'))
            return False
 
        context_hosts_aggregate = context['hosts_aggregate']
        for host in context_hosts_aggregate:
            try:
                api.nova.add_host_to_aggregate(request, self.object.id, host)
            except Exception:
                exceptions.handle(
                    request, _('Error adding Hosts to the source domain.'))
                return False

        return True
    
class SetControlCenterInfoStep(workflows.Step):
    action_class = SetControlCenterInfoAction
    contributes = ("name",
                   "domain_name",
                   "hostname",
                   "tenantname",
                   "username",
                   "passwd",
                   "virtualplatformtype",
                   "network_id",
                   "virtualplatformIP",
                   "virtualplatformusername",
                   "virtualplatformpassword")
    
class AddControlCenterWorkflow(workflows.Workflow):
    slug = "add_control_center"
    name = _("Add Control Center")
    finalize_button_name = _("Next")
    failure_message = _('Unable to add control center "%s".')
    success_url = constants.CONTROL_CENTER_CREATE_URL2
    default_steps = (SetControlCenterInfoStep, )
    wizard = True

    def handle(self, request, context):
        GlobalVars.control_center_info = context
        try:
            request_api = RequestApi()
            res = request_api.getRequestInfo('api/heterogeneous/platform',context)
            if res and not res.get('errormsg'):
                f_res = []
                for dc in res:
                    for cl in res[dc]:
                        val = '%s ( %s )' % (str(cl),str(dc))
                        f_res.append((val,val))
                GlobalVars.avilible_clusters = f_res
                return True
        except Exception:
            exceptions.handle(request, err_msg)
        return False

class AddControlCenterWorkflow2(workflows.Workflow):
    slug = "add_control_center"
    name = _("Add Control Center")
    finalize_button_name = _("Add Control Center")
    success_message = _('Added new control center "%s".')
    failure_message = _('Unable to add control center "%s".')
    success_url = constants.CONTROL_CENTER_INDEX_URL
    default_steps = (AddClustersToControlCenterStep, )
    wizard = True

    def handle(self, request, context):
        try:
            requestapi = RequestApi()
            res = requestapi.postRequestInfo('api/heterogeneous/platforms',context)
            if res.get('action') == 'success':
                return True
        except Exception as e:
            pass
        return False