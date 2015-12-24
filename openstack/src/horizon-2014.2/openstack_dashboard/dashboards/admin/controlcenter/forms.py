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

from horizon import exceptions
from horizon import forms
from horizon import messages

from openstack_dashboard import api
import json
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.log import operate_log

class UpdateSourceDomainInfoForm(forms.SelfHandlingForm):
    id = forms.CharField(widget=forms.HiddenInput)
    
    name = forms.CharField(label=_("Name"),
                           max_length=255)
    availability_zone = forms.CharField(label=_("Availability Zone"),
                                        max_length=255)

    def __init__(self, request, *args, **kwargs):
        super(UpdateSourceDomainInfoForm, self).__init__(request, *args, **kwargs)

    def clean(self):
        cleaned_data = super(UpdateSourceDomainInfoForm, self).clean()
        id = cleaned_data.get('id')
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
                if str(aggregate.id) != str(id) and aggregate.name.lower() == name.lower():
                    raise forms.ValidationError(
                        _('The name "%s" is already used by '
                          'another source domain.')
                        % name
                    )
                if str(aggregate.id) != str(id) and aggregate.availability_zone.lower() == availability_zone.lower():
                    raise forms.ValidationError(
                        _('The availability_zone "%s" is already used by '
                          'another source domain.')
                        % availability_zone
                    )
        return cleaned_data

    def handle(self, request, data):
        id = self.initial['id']
        name = data['name']
        availability_zone = data['availability_zone']
        aggregate = {'name': name}
        if availability_zone:
            aggregate['availability_zone'] = availability_zone
        try:
            api.nova.aggregate_update(request, id, aggregate)
            message = _('Successfully updated source domain: "%s."') \
                      % data['name']
            messages.success(request, message)
        except Exception:
            exceptions.handle(request,
                              _('Unable to update the source domain.'))
        return True

class SyncControlCenterForm(forms.SelfHandlingForm):
    tenantname = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    virtualplatformtype = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    domain_name = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    hostname = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    virtualplatformIP = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    datacentersandclusters = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    name = forms.CharField(label=_("hiddeninfo"),widget=forms.HiddenInput())
    
    network_id = forms.ChoiceField(label=_("Network Name"))
    username = forms.CharField(label=_("Cloud Platform Account"),
                               widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    passwd = forms.CharField(label=_("Cloud Platform Password"),
                             widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))
    virtualplatformusername = forms.CharField(label=_("Heterogeneous Platform Account"),
                               widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    virtualplatformpassword = forms.CharField(label=_("Heterogeneous Platform Password"),
                                              widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))
    
    def __init__(self, request, *args, **kwargs):
        super(SyncControlCenterForm, self).__init__(request, *args, **kwargs)
        networks = []
        try:
            _networks = api.neutron.network_list(self.request)
            networks = [(n.id,n.name) for n in _networks]
        except Exception:
            networks = []
            msg = _('Network list can not be retrieved.')
            exceptions.handle(request, msg)
        self.fields['network_id'].choices = networks

    def handle(self, request, data):
        try:
            requestapi = RequestApi()
            data['datacentersandclusters'] = json.loads(data['datacentersandclusters'])
            res = requestapi.postRequestInfo('api/heterogeneous/platforms/sync',data)
            if res.get('action') == 'success':
                messages.success(request,_('Success to synchronize the control center.'))
                return True
        except Exception as e:
            exceptions.handle(request,
                              _('Unable to synchronize the control center.'))
        return False
    
class DeleteControlCenterForm(forms.SelfHandlingForm):
    name = forms.CharField(widget=forms.HiddenInput(),
                           required=False)
    virtualplatformtype = forms.CharField(label=_("hiddeninfo"),
                                          widget=forms.HiddenInput(),
                                          required=False)
    tenantname = forms.CharField(label=_("Tenant Name"),widget=forms.HiddenInput())
    hostname = forms.CharField(label=_("Host"),widget=forms.HiddenInput())
    id = forms.CharField(widget=forms.HiddenInput())
    
    username = forms.CharField(label=_("Cloud Platform Account"),
                               widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    passwd = forms.CharField(label=_("Cloud Platform Password"),
                             widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))
    
    def __init__(self, request, *args, **kwargs):
        super(DeleteControlCenterForm, self).__init__(request, *args, **kwargs)
        

    def handle(self, request, data):
        try:
            requestapi = RequestApi()
            data['uuid'] = data.get('id')
            res = requestapi.deleteRequestInfo('api/heterogeneous/platforms/' + data.get('id'),data)
            if res and type(res) == type({}):
                if res.get('action') == 'success':
                    operate_log(request.user.username,
                                request.user.roles,
                                str(data.get("name")) + "synchronize date")
                    return True
                elif res.get('action') == 'failed' and res.get('is_auto') == True:
                    err_msg = 'The plat is syncing, you can not delete it.'
                    messages.error(request,_(err_msg))
                    return False
        except Exception as e:
            exceptions.handle(request,
                              _('Unable to synchronize the control center.'))
        return False