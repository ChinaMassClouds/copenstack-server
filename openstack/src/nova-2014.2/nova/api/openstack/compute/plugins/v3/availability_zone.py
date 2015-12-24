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

from oslo.config import cfg

from nova.api.openstack.compute.schemas.v3 import availability_zone as schema
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import availability_zones
from nova import objects
from nova import servicegroup

CONF = cfg.CONF
ALIAS = "os-availability-zone"
ATTRIBUTE_NAME = "availability_zone"
authorize_list = extensions.extension_authorizer('compute',
                                                 'v3:' + ALIAS + ':list')
authorize_detail = extensions.extension_authorizer('compute',
                                                   'v3:' + ALIAS + ':detail')


class AvailabilityZoneController(wsgi.Controller):
    """The Availability Zone API controller for the OpenStack API."""

    def __init__(self):
        super(AvailabilityZoneController, self).__init__()
        self.servicegroup_api = servicegroup.API()

    def _get_filtered_availability_zones(self, zones, is_available):
        result = []
        for zone in zones:
            # Hide internal_service_availability_zone
            if zone == CONF.internal_service_availability_zone:
                continue
            result.append({'zoneName': zone,
                           'zoneState': {'available': is_available},
                           "hosts": None})
        return result

    def _describe_availability_zones(self, context, **kwargs):
        ctxt = context.elevated()
        available_zones, not_available_zones = \
            availability_zones.get_availability_zones(ctxt)

        filtered_available_zones = \
            self._get_filtered_availability_zones(available_zones, True)
        filtered_not_available_zones = \
            self._get_filtered_availability_zones(not_available_zones, False)
        return {'availabilityZoneInfo': filtered_available_zones +
                                        filtered_not_available_zones}

    def _describe_availability_zones_verbose(self, context, **kwargs):
        ctxt = context.elevated()
        available_zones, not_available_zones = \
            availability_zones.get_availability_zones(ctxt)

        # Available services
        enabled_services = objects.ServiceList.get_all(context, disabled=False)
        enabled_services = availability_zones.set_availability_zones(context,
                enabled_services)
        zone_hosts = {}
        host_services = {}
        for service in enabled_services:
            zone_hosts.setdefault(service['availability_zone'], [])
            if service['host'] not in zone_hosts[service['availability_zone']]:
                zone_hosts[service['availability_zone']].append(
                    service['host'])

            host_services.setdefault(service['availability_zone'] +
                    service['host'], [])
            host_services[service['availability_zone'] + service['host']].\
                    append(service)

        result = []
        for zone in available_zones:
            hosts = {}
            for host in zone_hosts.get(zone, []):
                hosts[host] = {}
                for service in host_services[zone + host]:
                    alive = self.servicegroup_api.service_is_up(service)
                    hosts[host][service['binary']] = {'available': alive,
                                      'active': True != service['disabled'],
                                      'updated_at': service['updated_at']}
            result.append({'zoneName': zone,
                           'zoneState': {'available': True},
                           "hosts": hosts})

        for zone in not_available_zones:
            result.append({'zoneName': zone,
                           'zoneState': {'available': False},
                           "hosts": None})
        return {'availabilityZoneInfo': result}

    @extensions.expected_errors(())
    def index(self, req):
        """Returns a summary list of availability zone."""
        context = req.environ['nova.context']
        authorize_list(context)

        return self._describe_availability_zones(context)

    @extensions.expected_errors(())
    def detail(self, req):
        """Returns a detailed list of availability zone."""
        context = req.environ['nova.context']
        authorize_detail(context)

        return self._describe_availability_zones_verbose(context)


class AvailabilityZone(extensions.V3APIExtensionBase):
    """1. Add availability_zone to the Create Server API.
       2. Add availability zones describing.
    """

    name = "AvailabilityZone"
    alias = ALIAS
    version = 1

    def get_resources(self):
        resource = [extensions.ResourceExtension(ALIAS,
            AvailabilityZoneController(),
            collection_actions={'detail': 'GET'})]
        return resource

    def get_controller_extensions(self):
        """It's an abstract function V3APIExtensionBase and the extension
        will not be loaded without it.
        """
        return []

    # NOTE(gmann): This function is not supposed to use 'body_deprecated_param'
    # parameter as this is placed to handle scheduler_hint extension for V2.1.
    def server_create(self, server_dict, create_kwargs, body_deprecated_param):
        create_kwargs['availability_zone'] = server_dict.get(ATTRIBUTE_NAME)

    def get_server_create_schema(self):
        return schema.server_create
