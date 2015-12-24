# Copyright 2012 OpenStack Foundation
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

import webob

from nova.api.openstack import common
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import compute
from nova import exception
from nova.i18n import _


authorize = extensions.extension_authorizer('compute', 'consoles')


class MassCloudsConsolesController(wsgi.Controller):
    def __init__(self, *args, **kwargs):
        self.compute_api = compute.API()
        super(MassCloudsConsolesController, self).__init__(*args, **kwargs)

    @wsgi.action('os-getSPICEConnectInfo')
    def get_spice_connect_info(self, req, id, body):
        """Get spice port information to access a server."""
        context = req.environ['nova.context']
        authorize(context)

        # If type is not supplied or unknown, get_spice_console below will cope
        console_type = body['os-getSPICEConnectInfo'].get('type')
        instance = common.get_instance(self.compute_api, context, id,
                                       want_objects=True)

        try:
            output = self.compute_api.get_spice_connect_info(context,
                                                      instance,
                                                      console_type)
        except exception.ConsoleTypeUnavailable as e:
            raise webob.exc.HTTPBadRequest(explanation=e.format_message())
        except exception.InstanceNotReady as e:
            raise webob.exc.HTTPConflict(explanation=e.format_message())
        except NotImplementedError:
            msg = _("Unable to get spice console, "
                    "functionality not implemented")
            raise webob.exc.HTTPNotImplemented(explanation=msg)

        return {'console': {'host': output['host'], 'port': output['port']}}

class Massclouds_console(extensions.ExtensionDescriptor):
    """Interactive Console support."""
    name = "MassCloudsConsoles"
    alias = "os-massclouds-consoles"
    namespace = "http://docs.openstack.org/compute/ext/os-consoles/api/v2"
    updated = "2011-12-23T00:00:00Z"

    def get_controller_extensions(self):
        controller = MassCloudsConsolesController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]
