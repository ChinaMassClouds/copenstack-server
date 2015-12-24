# Copyright 2011 University of Southern California
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

"""The instance type extra specs extension."""

import six
from webob import exc

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova.compute import flavors
from nova import exception
from nova.i18n import _
from nova import objects
from nova import utils

authorize = extensions.extension_authorizer('compute', 'flavorextraspecs')


class ExtraSpecsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        extra_specs_dict = xmlutil.make_flat_dict('extra_specs', colon_ns=True)
        return xmlutil.MasterTemplate(extra_specs_dict, 1)


class ExtraSpecTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        sel = xmlutil.Selector(xmlutil.get_items, 0)
        root = xmlutil.TemplateElement('extra_spec', selector=sel)
        root.set('key', 0)
        root.text = 1
        return xmlutil.MasterTemplate(root, 1)


class FlavorExtraSpecsController(object):
    """The flavor extra specs API controller for the OpenStack API."""

    def _get_extra_specs(self, context, flavor_id):
        flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
        return dict(extra_specs=flavor.extra_specs)

    def _check_body(self, body):
        if body is None or body == "":
            expl = _('No Request Body')
            raise exc.HTTPBadRequest(explanation=expl)

    def _check_extra_specs(self, specs):
        if type(specs) is not dict:
            msg = _('Bad extra_specs provided')
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            flavors.validate_extra_spec_keys(specs.keys())
        except TypeError:
            msg = _("Fail to validate provided extra specs keys. "
                    "Expected string")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.InvalidInput as error:
            raise exc.HTTPBadRequest(explanation=error.format_message())

        for key, value in specs.iteritems():
            try:
                utils.check_string_length(key, 'extra_specs key',
                                          min_length=1, max_length=255)

                # NOTE(dims): The following check was added for backwards
                # compatibility.
                if (isinstance(value, (int, long, float))):
                    value = six.text_type(value)
                utils.check_string_length(value, 'extra_specs value',
                                          max_length=255)
            except exception.InvalidInput as error:
                raise exc.HTTPBadRequest(explanation=error.format_message())

    @wsgi.serializers(xml=ExtraSpecsTemplate)
    def index(self, req, flavor_id):
        """Returns the list of extra specs for a given flavor."""
        context = req.environ['nova.context']
        authorize(context, action='index')
        return self._get_extra_specs(context, flavor_id)

    @wsgi.serializers(xml=ExtraSpecsTemplate)
    def create(self, req, flavor_id, body):
        context = req.environ['nova.context']
        authorize(context, action='create')
        self._check_body(body)
        specs = body.get('extra_specs')
        self._check_extra_specs(specs)
        try:
            flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
            flavor.extra_specs = dict(flavor.extra_specs, **specs)
            flavor.save()
        except exception.FlavorExtraSpecUpdateCreateFailed as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.FlavorNotFound as error:
            raise exc.HTTPNotFound(explanation=error.format_message())
        return body

    @wsgi.serializers(xml=ExtraSpecTemplate)
    def update(self, req, flavor_id, id, body):
        context = req.environ['nova.context']
        authorize(context, action='update')
        self._check_extra_specs(body)
        if id not in body:
            expl = _('Request body and URI mismatch')
            raise exc.HTTPBadRequest(explanation=expl)
        if len(body) > 1:
            expl = _('Request body contains too many items')
            raise exc.HTTPBadRequest(explanation=expl)
        try:
            flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
            flavor.extra_specs = dict(flavor.extra_specs, **body)
            flavor.save()
        except exception.FlavorExtraSpecUpdateCreateFailed as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.FlavorNotFound as error:
            raise exc.HTTPNotFound(explanation=error.format_message())
        return body

    @wsgi.serializers(xml=ExtraSpecTemplate)
    def show(self, req, flavor_id, id):
        """Return a single extra spec item."""
        context = req.environ['nova.context']
        authorize(context, action='show')
        try:
            flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
            return {id: flavor.extra_specs[id]}
        except exception.FlavorNotFound as error:
            raise exc.HTTPNotFound(explanation=error.format_message())
        except KeyError:
            msg = _("Flavor %(flavor_id)s has no extra specs with "
                    "key %(key)s.") % dict(flavor_id=flavor_id,
                                           key=id)
            raise exc.HTTPNotFound(explanation=msg)

    def delete(self, req, flavor_id, id):
        """Deletes an existing extra spec."""
        context = req.environ['nova.context']
        authorize(context, action='delete')
        try:
            flavor = objects.Flavor.get_by_flavor_id(context, flavor_id)
            del flavor.extra_specs[id]
            flavor.save()
        except exception.FlavorNotFound as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except KeyError:
            msg = _("Flavor %(flavor_id)s has no extra specs with "
                    "key %(key)s.") % dict(flavor_id=flavor_id,
                                           key=id)
            raise exc.HTTPNotFound(explanation=msg)


class Flavorextraspecs(extensions.ExtensionDescriptor):
    """Instance type (flavor) extra specs."""

    name = "FlavorExtraSpecs"
    alias = "os-flavor-extra-specs"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "flavor_extra_specs/api/v1.1")
    updated = "2011-06-23T00:00:00Z"

    def get_resources(self):
        resources = []

        res = extensions.ResourceExtension(
                'os-extra_specs',
                FlavorExtraSpecsController(),
                parent=dict(member_name='flavor', collection_name='flavors'))

        resources.append(res)
        return resources
