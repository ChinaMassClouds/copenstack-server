# Copyright 2014 NEC Corporation.  All rights reserved.
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

create = {
    'type': 'object',
    'properties': {
        'interfaceAttachment': {
            'type': 'object',
            'properties': {
                'net_id': {
                    # NOTE: This parameter is passed to the search_opts of
                    # Neutron list_network API: search_opts = {'id': net_id}
                    # A network id should be uuid.
                    'type': 'string', 'format': 'uuid',
                },
                'port_id': {
                    # NOTE: This parameter is passed to Neutron show_port API
                    # as a port id. A port id should be uuid.
                    'type': 'string', 'format': 'uuid',
                },
                'fixed_ips': {
                    'type': 'array', 'minItems': 1, 'maxItems': 1,
                    'items': {
                        'type': 'object',
                        'properties': {
                            'ip_address': {
                                'type': 'string',
                                'oneOf': [
                                    {'format': 'ipv4'},
                                    {'format': 'ipv6'}
                                ],
                            },
                        },
                        'required': ['ip_address'],
                        'additionalProperties': False,
                    },
                },
            },
            'additionalProperties': False,
        },
    },
    'additionalProperties': False,
}
