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
from openstack_dashboard.openstack.common.log import policy_is
import horizon


class SystemPanels(horizon.PanelGroup):
    slug = "admin"
    name = "System"
    panels = ('overview', 'metering', 'hypervisors', 'aggregates',
              'instances', 'volumes', 'flavors', 'images',
              'networks', 'routers', 'defaults', 'info')

class TakeoverPanels(horizon.PanelGroup):
    slug = "takeover"
    name = "TakeOver"
    panels = ('controlcenter', 'datacenter','clusters','host')



class CheckPanels(horizon.PanelGroup):
    slug = "check"
    name = "Check"
    panels = ('checkhost', 'checkdisk')

class MonitorPanels(horizon.PanelGroup):
    slug = "monitor"
    name = "Monitor_And_Alarm"
    panels = ('logictopo','monitoroverview','monitorstatus', 'alarmmsg','alarmpolicy')

class LogPanels(horizon.PanelGroup):
    slug = "log"
    name = "Log"
    panels = ('log',)



class Admin(horizon.Dashboard):
    name = _("Admin")
    slug = "admin"
    panels = (SystemPanels,TakeoverPanels,CheckPanels,MonitorPanels,LogPanels)
    default_panel = 'overview'
    img = '/static/dashboard/img/nav/Dashboard_admin.png'

    def nav(self, context):
        username = context['request'].user.username
        return policy_is(username, 'appradmin', 'auditadmin', 'sysadmin', 'admin','syncadmin')


horizon.register(Admin)
