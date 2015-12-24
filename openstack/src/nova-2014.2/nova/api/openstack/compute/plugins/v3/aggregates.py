# Copyright (c) 2012 Citrix Systems, Inc.
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

"""The Aggregate admin API extension."""

import datetime

from webob import exc

from nova.api.openstack.compute.schemas.v3 import aggregates
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api import validation
from nova.compute import api as compute_api
from nova import exception
from nova.i18n import _
from nova import utils

ALIAS = "os-aggregates"
authorize = extensions.extension_authorizer('compute', "v3:" + ALIAS)


def _get_context(req):
    return req.environ['nova.context']


class AggregateController(wsgi.Controller):
    """The Host Aggregates API controller for the OpenStack API."""
    def __init__(self):
        self.api = compute_api.AggregateAPI()

    @extensions.expected_errors(())
    def index(self, req):
        """Returns a list a host aggregate's id, name, availability_zone."""
        context = _get_context(req)
        authorize(context, action='index')
        aggregates = self.api.get_aggregate_list(context)
        return {'aggregates': [self._marshall_aggregate(a)['aggregate']
                               for a in aggregates]}

    # NOTE(gmann): Returns 200 for backwards compatibility but should be 201
    # as this operation complete the creation of aggregates resource.
    @extensions.expected_errors((400, 409))
    @validation.schema(aggregates.create)
    def create(self, req, body):
        """Creates an aggregate, given its name and
        optional availability zone.
        """
        context = _get_context(req)
        authorize(context, action='create')
        host_aggregate = body["aggregate"]
        name = host_aggregate["name"]
        avail_zone = host_aggregate.get("availability_zone")

        try:
            aggregate = self.api.create_aggregate(context, name, avail_zone)
        except exception.AggregateNameExists as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.InvalidAggregateAction as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())
        return self._marshall_aggregate(aggregate)

    @extensions.expected_errors(404)
    def show(self, req, id):
        """Shows the details of an aggregate, hosts and metadata included."""
        context = _get_context(req)
        authorize(context, action='show')
        try:
            aggregate = self.api.get_aggregate(context, id)
        except exception.AggregateNotFound as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        return self._marshall_aggregate(aggregate)

    @extensions.expected_errors((400, 404, 409))
    @validation.schema(aggregates.update)
    def update(self, req, id, body):
        """Updates the name and/or availability_zone of given aggregate."""
        context = _get_context(req)
        authorize(context, action='update')
        updates = body["aggregate"]

        try:
            aggregate = self.api.update_aggregate(context, id, updates)
        except exception.AggregateNameExists as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.AggregateNotFound as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except exception.InvalidAggregateAction as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

        return self._marshall_aggregate(aggregate)

    # NOTE(gmann): Returns 200 for backwards compatibility but should be 204
    # as this operation complete the deletion of aggregate resource and return
    # no response body.
    @extensions.expected_errors((400, 404))
    def delete(self, req, id):
        """Removes an aggregate by id."""
        context = _get_context(req)
        authorize(context, action='delete')
        try:
            self.api.delete_aggregate(context, id)
        except exception.AggregateNotFound as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except exception.InvalidAggregateAction as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

    # NOTE(gmann): Returns 200 for backwards compatibility but should be 202
    # for representing async API as this API just accepts the request and
    # request hypervisor driver to complete the same in async mode.
    @extensions.expected_errors((400, 404, 409))
    @wsgi.action('add_host')
    @validation.schema(aggregates.add_host)
    def _add_host(self, req, id, body):
        """Adds a host to the specified aggregate."""
        host = body['add_host']['host']

        context = _get_context(req)
        authorize(context, action='add_host')
        try:
            aggregate = self.api.add_host_to_aggregate(context, id, host)
        except (exception.AggregateNotFound,
                exception.ComputeHostNotFound) as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except (exception.AggregateHostExists,
                exception.InvalidAggregateAction) as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        return self._marshall_aggregate(aggregate)

    # NOTE(gmann): Returns 200 for backwards compatibility but should be 202
    # for representing async API as this API just accepts the request and
    # request hypervisor driver to complete the same in async mode.
    @extensions.expected_errors((400, 404, 409))
    @wsgi.action('remove_host')
    @validation.schema(aggregates.remove_host)
    def _remove_host(self, req, id, body):
        """Removes a host from the specified aggregate."""
        host = body['remove_host']['host']

        context = _get_context(req)
        authorize(context, action='remove_host')
        try:
            aggregate = self.api.remove_host_from_aggregate(context, id, host)
        except (exception.AggregateNotFound, exception.AggregateHostNotFound,
                exception.ComputeHostNotFound):
            msg = _('Cannot remove host %(host)s in aggregate %(id)s') % {
                        'host': host, 'id': id}
            raise exc.HTTPNotFound(explanation=msg)
        except exception.InvalidAggregateAction:
            msg = _('Cannot remove host %(host)s in aggregate %(id)s') % {
                        'host': host, 'id': id}
            raise exc.HTTPConflict(explanation=msg)
        return self._marshall_aggregate(aggregate)

    @extensions.expected_errors((400, 404))
    @wsgi.action('set_metadata')
    def _set_metadata(self, req, id, body):
        """Replaces the aggregate's existing metadata with new metadata."""
        context = _get_context(req)
        authorize(context, action='set_metadata')
        if not self.is_valid_body(body, 'set_metadata'):
            raise exc.HTTPBadRequest(explanation=_("Invalid request body"))
        if not self.is_valid_body(body["set_metadata"], "metadata"):
            raise exc.HTTPBadRequest(
                explanation=_("Invalid request format for metadata"))
        metadata = body["set_metadata"]["metadata"]

        # The metadata should be a dict
        if not isinstance(metadata, dict):
            msg = _('The value of metadata must be a dict')
            raise exc.HTTPBadRequest(explanation=msg)
        try:
            for key, value in metadata.items():
                utils.check_string_length(key, "metadata.key", 1, 255)
                if value is not None:
                    utils.check_string_length(value, "metadata.value", 0, 255)
        except exception.InvalidInput as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())
        try:
            aggregate = self.api.update_aggregate_metadata(context,
                                                           id, metadata)
        except exception.AggregateNotFound as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except exception.InvalidAggregateAction as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

        return self._marshall_aggregate(aggregate)

    def _marshall_aggregate(self, aggregate):
        _aggregate = {}
        for key, value in aggregate.items():
            # NOTE(danms): The original API specified non-TZ-aware timestamps
            if isinstance(value, datetime.datetime):
                value = value.replace(tzinfo=None)
            _aggregate[key] = value
        return {"aggregate": _aggregate}


class Aggregates(extensions.V3APIExtensionBase):
    """Admin-only aggregate administration."""

    name = "Aggregates"
    alias = ALIAS
    version = 1

    def get_resources(self):
        resources = [extensions.ResourceExtension(
                                            self.alias,
                                            AggregateController(),
                                            member_actions={'action': 'POST'})]
        return resources

    def get_controller_extensions(self):
        return []
