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


from django.conf.urls import patterns
from django.conf.urls import url

from openstack_dashboard.dashboards.admin.controlcenter import views


urlpatterns = patterns('openstack_dashboard.dashboards.admin.controlcenter.views',
    url(r'^$', views.IndexView.as_view(), name='index'),
    url(r'^add_source_domain/$', views.SourceDomainCreateView.as_view(), name='add_source_domain'),
    url(r'^(?P<id>[^/]+)/sync/$', views.ControlCenterSyncView.as_view(), name='sync'),
    url(r'^(?P<id>[^/]+)/delete/$', views.ControlCenterDeleteView.as_view(), name='delete'),
    url(r'^add_control_center/$', views.ControlCenterCreateView.as_view(), name='add_control_center'),
    url(r'^add_control_center2/$', views.ControlCenterCreateView2.as_view(), name='add_control_center2'),
    url(r'^(?P<id>[^/]+)/update/$',
        views.SourceDomainUpdateView.as_view(), name='update_source_domain'),
    url(r'^(?P<id>[^/]+)/manage_hosts/$',
        views.ManageHostsView.as_view(), name='manage_hosts'),
    url(r'^(?P<domain_id>[^/]+)/domain_hosts/$','domain_hosts', name='domain_hosts'),
    url(r'^(?P<domain_id>[^/]+)/domain_vms/$','domain_vms', name='domain_vms'),
)
