# Copyright 2012 OpenStack Foundation
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

import webob

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
import nova.context
from nova import db
from nova import exception
from nova.i18n import _
from nova import quota
from nova import utils


QUOTAS = quota.QUOTAS
# Quotas that are only enabled by specific extensions
EXTENDED_QUOTAS = {'server_groups': 'os-server-group-quotas',
                   'server_group_members': 'os-server-group-quotas'}


authorize = extensions.extension_authorizer('compute', 'quota_classes')


class QuotaClassTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('quota_class_set',
                                       selector='quota_class_set')
        root.set('id')

        for resource in QUOTAS.resources:
            if resource not in EXTENDED_QUOTAS:
                elem = xmlutil.SubTemplateElement(root, resource)
                elem.text = resource

        return xmlutil.MasterTemplate(root, 1)


class QuotaClassSetsController(wsgi.Controller):

    supported_quotas = []

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self.supported_quotas = QUOTAS.resources
        for resource, extension in EXTENDED_QUOTAS.items():
            if not self.ext_mgr.is_loaded(extension):
                self.supported_quotas.remove(resource)

    def _format_quota_set(self, quota_class, quota_set):
        """Convert the quota object to a result dict."""

        if quota_class:
            result = dict(id=str(quota_class))
        else:
            result = {}

        for resource in self.supported_quotas:
            if resource in quota_set:
                result[resource] = quota_set[resource]

        return dict(quota_class_set=result)

    @wsgi.serializers(xml=QuotaClassTemplate)
    def show(self, req, id):
        context = req.environ['nova.context']
        authorize(context)
        try:
            nova.context.authorize_quota_class_context(context, id)
            values = QUOTAS.get_class_quotas(context, id)
            return self._format_quota_set(id, values)
        except exception.Forbidden:
            raise webob.exc.HTTPForbidden()

    @wsgi.serializers(xml=QuotaClassTemplate)
    def update(self, req, id, body):
        context = req.environ['nova.context']
        authorize(context)
        quota_class = id
        bad_keys = []

        if not self.is_valid_body(body, 'quota_class_set'):
            msg = _("quota_class_set not specified")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        quota_class_set = body['quota_class_set']
        for key in quota_class_set.keys():
            if key not in self.supported_quotas:
                bad_keys.append(key)
                continue
            try:
                value = utils.validate_integer(
                        body['quota_class_set'][key], key)
            except exception.InvalidInput as e:
                raise webob.exc.HTTPBadRequest(
                    explanation=e.format_message())

        if bad_keys:
            msg = _("Bad key(s) %s in quota_set") % ",".join(bad_keys)
            raise webob.exc.HTTPBadRequest(explanation=msg)

        for key in quota_class_set.keys():
            value = utils.validate_integer(
                        body['quota_class_set'][key], key)
            try:
                db.quota_class_update(context, quota_class, key, value)
            except exception.QuotaClassNotFound:
                db.quota_class_create(context, quota_class, key, value)
            except exception.AdminRequired:
                raise webob.exc.HTTPForbidden()

        values = QUOTAS.get_class_quotas(context, quota_class)
        return self._format_quota_set(None, values)


class Quota_classes(extensions.ExtensionDescriptor):
    """Quota classes management support."""

    name = "QuotaClasses"
    alias = "os-quota-class-sets"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "quota-classes-sets/api/v1.1")
    updated = "2012-03-12T00:00:00Z"

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension('os-quota-class-sets',
                                    QuotaClassSetsController(self.ext_mgr))
        resources.append(res)

        return resources
