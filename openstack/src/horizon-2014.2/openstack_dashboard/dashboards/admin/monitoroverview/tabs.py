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

from django import template
from django.utils.translation import ugettext_lazy as _

from horizon import messages
from horizon import tabs

from openstack_dashboard import api
from openstack_dashboard.api import ceilometer

class VmTab(tabs.Tab):
    name = _("VM")
    slug = "vm"
    template_name = ("admin/monitoroverview/vm_tab.html")
    
    def get_context_data(self, request):
        context = template.RequestContext(request)
        return context

class HostTab(tabs.Tab):
    name = _("Host")
    slug = "host"
    template_name = ("admin/monitoroverview/host_tab.html")
    
    def get_context_data(self, request):
        context = template.RequestContext(request)
        return context
    
class CeilometerOverviewTabs(tabs.TabGroup):
    slug = "ceilometer_overview"
    tabs = (HostTab, VmTab, )
    sticky = True
