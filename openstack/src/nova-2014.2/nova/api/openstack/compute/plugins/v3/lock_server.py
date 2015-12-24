# Copyright 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
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

import webob

from nova.api.openstack import common
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import compute

ALIAS = "os-lock-server"


def authorize(context, action_name):
    action = 'v3:%s:%s' % (ALIAS, action_name)
    extensions.extension_authorizer('compute', action)(context)


class LockServerController(wsgi.Controller):
    def __init__(self, *args, **kwargs):
        super(LockServerController, self).__init__(*args, **kwargs)
        self.compute_api = compute.API()

    @extensions.expected_errors(404)
    @wsgi.action('lock')
    def _lock(self, req, id, body):
        """Lock a server instance."""
        context = req.environ['nova.context']
        authorize(context, 'lock')
        instance = common.get_instance(self.compute_api, context, id,
                                       want_objects=True)
        self.compute_api.lock(context, instance)
        return webob.Response(status_int=202)

    @extensions.expected_errors(404)
    @wsgi.action('unlock')
    def _unlock(self, req, id, body):
        """Unlock a server instance."""
        context = req.environ['nova.context']
        authorize(context, 'unlock')
        instance = common.get_instance(self.compute_api, context, id,
                                       want_objects=True)
        self.compute_api.unlock(context, instance)
        return webob.Response(status_int=202)


class LockServer(extensions.V3APIExtensionBase):
    """Enable lock/unlock server actions."""

    name = "LockServer"
    alias = ALIAS
    version = 1

    def get_controller_extensions(self):
        controller = LockServerController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]

    def get_resources(self):
        return []
