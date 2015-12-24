# Copyright 2014 Hewlett-Packard Development Company, L.P.
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


class Identity(horizon.Dashboard):
    name = _("Identity")
    slug = "identity"
    default_panel = 'projects'
    img = '/static/dashboard/img/nav/Dashboard_identity.png'
    panels = ('domains', 'projects', 'users', 'groups', 'roles',)

    def nav(self, context):
        username = context['request'].user.username
        return policy_is(username, 'sysadmin', 'admin')


horizon.register(Identity)
