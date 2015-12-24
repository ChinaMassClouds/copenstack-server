#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.


from nova.api.openstack import extensions


class Extended_evacuate_find_host(extensions.ExtensionDescriptor):
    """Enables server evacuation without target host. Scheduler will select
       one to target.
    """
    name = "ExtendedEvacuateFindHost"
    alias = "os-extended-evacuate-find-host"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "extended_evacuate_find_host/api/v2")
    updated = "2014-02-12T00:00:00Z"
