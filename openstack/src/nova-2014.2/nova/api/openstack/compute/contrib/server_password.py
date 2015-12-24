# Copyright (c) 2012 Nebula, Inc.
# All Rights Reserved.
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

"""The server password extension."""

import webob

from nova.api.metadata import password
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import compute
from nova import exception


authorize = extensions.extension_authorizer('compute', 'server_password')


class ServerPasswordTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('password', selector='password')
        root.text = unicode
        return xmlutil.MasterTemplate(root, 1)


class ServerPasswordController(object):
    """The Server Password API controller for the OpenStack API."""
    def __init__(self):
        self.compute_api = compute.API()

    def _get_instance(self, context, server_id):
        try:
            return self.compute_api.get(context, server_id, want_objects=True)
        except exception.InstanceNotFound as exp:
            raise webob.exc.HTTPNotFound(explanation=exp.format_message())

    @wsgi.serializers(xml=ServerPasswordTemplate)
    def index(self, req, server_id):
        context = req.environ['nova.context']
        authorize(context)
        instance = self._get_instance(context, server_id)

        passw = password.extract_password(instance)
        return {'password': passw or ''}

    @wsgi.response(204)
    def delete(self, req, server_id):
        context = req.environ['nova.context']
        authorize(context)
        instance = self._get_instance(context, server_id)
        meta = password.convert_password(context, None)
        instance.system_metadata.update(meta)
        instance.save()


class Server_password(extensions.ExtensionDescriptor):
    """Server password support."""

    name = "ServerPassword"
    alias = "os-server-password"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "server-password/api/v2")
    updated = "2012-11-29T00:00:00Z"

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension(
            'os-server-password',
            controller=ServerPasswordController(),
            collection_actions={'delete': 'DELETE'},
            parent=dict(member_name='server', collection_name='servers'))
        resources.append(res)

        return resources
