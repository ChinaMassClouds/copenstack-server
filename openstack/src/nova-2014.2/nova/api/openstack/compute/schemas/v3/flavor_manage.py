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

from nova.api.validation import parameter_types

create = {
    'type': 'object',
    'properties': {
        'flavor': {
            'type': 'object',
            'properties': {
                # in nova/flavors.py, name with all white spaces is forbidden.
                'name': parameter_types.name,
                # forbid leading/trailing whitespaces
                'id': {
                    'type': ['string', 'number', 'null'],
                    'minLength': 1, 'maxLength': 255,
                    'pattern': '^(?! )[a-zA-Z0-9. _-]+(?<! )$'
                },
                # positive ( > 0) integer
                'ram': {
                    'type': ['integer', 'string'],
                    'pattern': '^[0-9]*$', 'minimum': 1
                },
                # positive ( > 0) integer
                'vcpus': {
                    'type': ['integer', 'string'],
                    'pattern': '^[0-9]*$', 'minimum': 1
                },
                # non-negative ( >= 0) integer
                'disk': {
                    'type': ['integer', 'string'],
                    'pattern': '^[0-9]*$', 'minimum': 0
                },
                # non-negative ( >= 0) integer
                'OS-FLV-EXT-DATA:ephemeral': {
                    'type': ['integer', 'string'],
                    'pattern': '^[0-9]*$', 'minimum': 0
                },
                # non-negative ( >= 0) integer
                'swap': {
                    'type': ['integer', 'string'],
                    'pattern': '^[0-9]*$', 'minimum': 0
                },
                # positive ( > 0) float
                'rxtx_factor': {
                    'type': ['number', 'string'],
                    'pattern': '^[0-9]+(\.[0-9]+)?$',
                    'minimum': 0, 'exclusiveMinimum': True
                },
                'os-flavor-access:is_public': parameter_types.boolean,
            },
            # TODO(oomichi): 'id' should be required with v2.1+microversions.
            # On v2.0 API, nova-api generates a flavor-id automatically if
            # specifying null as 'id' or not specifying 'id'. Ideally a client
            # should specify null as 'id' for requesting auto-generated id
            # exactly. However, this strict limitation causes a backwards
            # incompatible issue on v2.1. So now here relaxes the requirement
            # of 'id'.
            'required': ['name', 'ram', 'vcpus', 'disk'],
            'additionalProperties': False,
        },
    },
    'required': ['flavor'],
    'additionalProperties': False,
}
