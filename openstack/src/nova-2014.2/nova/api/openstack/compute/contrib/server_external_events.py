# Copyright 2014 Red Hat, Inc.
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
from nova import compute
from nova import exception
from nova.i18n import _
from nova import objects
from nova.objects import external_event as external_event_obj
from nova.openstack.common import log as logging


LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('compute',
                                            'os-server-external-events')


class EventTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('events')
        elem1 = xmlutil.SubTemplateElement(root, 'event', selector='events')
        elem2 = xmlutil.SubTemplateElement(elem1, xmlutil.Selector(0),
                                           selector=xmlutil.get_items)
        elem2.text = 1
        return xmlutil.MasterTemplate(root, 1)


class EventDeserializer(wsgi.MetadataXMLDeserializer):
    def _extract_event(self, event_node):
        event = {}
        for key in ('name', 'tag', 'server_uuid', 'status'):
            node = self.find_first_child_named(event_node, key)
            event[key] = self.extract_text(node)
        return event

    def default(self, string):
        events = []
        dom = xmlutil.safe_minidom_parse_string(string)
        events_node = self.find_first_child_named(dom, 'events')
        for event_node in self.find_children_named(events_node, 'event'):
            events.append(self._extract_event(event_node))
        return {'body': {'events': events}}


class ServerExternalEventsController(wsgi.Controller):

    def __init__(self):
        self.compute_api = compute.API()
        super(ServerExternalEventsController, self).__init__()

    @wsgi.deserializers(xml=EventDeserializer)
    @wsgi.serializers(xml=EventTemplate)
    def create(self, req, body):
        """Creates a new instance event."""
        context = req.environ['nova.context']
        authorize(context, action='create')

        response_events = []
        accepted_events = []
        accepted_instances = set()
        instances = {}
        result = 200

        body_events = body.get('events', [])
        if not isinstance(body_events, list) or not len(body_events):
            raise webob.exc.HTTPBadRequest()

        for _event in body_events:
            client_event = dict(_event)
            event = objects.InstanceExternalEvent(context)

            try:
                event.instance_uuid = client_event.pop('server_uuid')
                event.name = client_event.pop('name')
                event.status = client_event.pop('status', 'completed')
                event.tag = client_event.pop('tag', None)
            except KeyError as missing_key:
                msg = _('event entity requires key %(key)s') % missing_key
                raise webob.exc.HTTPBadRequest(explanation=msg)

            if client_event:
                msg = (_('event entity contains unsupported items: %s') %
                       ', '.join(client_event.keys()))
                raise webob.exc.HTTPBadRequest(explanation=msg)

            if event.status not in external_event_obj.EVENT_STATUSES:
                raise webob.exc.HTTPBadRequest(
                    _('Invalid event status `%s\'') % event.status)

            instance = instances.get(event.instance_uuid)
            if not instance:
                try:
                    instance = objects.Instance.get_by_uuid(
                        context, event.instance_uuid)
                    instances[event.instance_uuid] = instance
                except exception.InstanceNotFound:
                    LOG.debug('Dropping event %(name)s:%(tag)s for unknown '
                              'instance %(instance_uuid)s',
                              dict(event.iteritems()))
                    _event['status'] = 'failed'
                    _event['code'] = 404
                    result = 207

            # NOTE: before accepting the event, make sure the instance
            # for which the event is sent is assigned to a host; otherwise
            # it will not be possible to dispatch the event
            if instance:
                if instance.host:
                    accepted_events.append(event)
                    accepted_instances.add(instance)
                    LOG.audit(_('Creating event %(name)s:%(tag)s for instance '
                                '%(instance_uuid)s'),
                              dict(event.iteritems()))
                    # NOTE: as the event is processed asynchronously verify
                    # whether 202 is a more suitable response code than 200
                    _event['status'] = 'completed'
                    _event['code'] = 200
                else:
                    LOG.debug("Unable to find a host for instance "
                              "%(instance)s. Dropping event %(event)s",
                              {'instance': event.instance_uuid,
                               'event': event.name})
                    _event['status'] = 'failed'
                    _event['code'] = 422
                    result = 207

            response_events.append(_event)

        if accepted_events:
            self.compute_api.external_instance_event(
                context, accepted_instances, accepted_events)
        else:
            msg = _('No instances found for any event')
            raise webob.exc.HTTPNotFound(explanation=msg)

        # FIXME(cyeoh): This needs some infrastructure support so that
        # we have a general way to do this
        robj = wsgi.ResponseObject({'events': response_events})
        robj._code = result
        return robj


class Server_external_events(extensions.ExtensionDescriptor):
    """Server External Event Triggers."""

    name = "ServerExternalEvents"
    alias = "os-server-external-events"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "server-external-events/api/v2")
    updated = "2014-02-18T00:00:00Z"

    def get_resources(self):
        resource = extensions.ResourceExtension('os-server-external-events',
                ServerExternalEventsController())

        return [resource]
