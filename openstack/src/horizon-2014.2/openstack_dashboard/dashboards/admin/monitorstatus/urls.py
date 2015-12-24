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

from django.conf.urls import patterns
from django.conf.urls import url

from openstack_dashboard.dashboards.admin.monitorstatus import views

urlpatterns = patterns('openstack_dashboard.dashboards.admin.monitorstatus.views',
    url(r'^$', views.IndexView.as_view(), name='index'),
    url(r'^cpu_monitor$', views.CpuMonitorView.as_view(), name='cpu_monitor'),
    url(r'^mem_monitor$', views.MemMonitorView.as_view(), name='mem_monitor'),
    url(r'^net_monitor$', views.NetMonitorView.as_view(), name='net_monitor'),
    url(r'^disk_monitor$', views.DiskMonitorView.as_view(), name='disk_monitor'),
)
