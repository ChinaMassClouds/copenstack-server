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

common_quota = {
    'type': ['integer', 'string'],
    'pattern': '^-?[0-9]+$',
    # -1 is a flag value for unlimited
    'minimum': -1
}

update = {
    'type': 'object',
    'properties': {
        'type': 'object',
        'quota_set': {
            'properties': {
                'instances': common_quota,
                'cores': common_quota,
                'ram': common_quota,
                'floating_ips': common_quota,
                'fixed_ips': common_quota,
                'metadata_items': common_quota,
                'key_pairs': common_quota,
                'security_groups': common_quota,
                'security_group_rules': common_quota,
                'injected_files': common_quota,
                'injected_file_content_bytes': common_quota,
                'injected_file_path_bytes': common_quota,
                'server_groups': common_quota,
                'server_group_members': common_quota,
                'force': parameter_types.boolean,
            },
            'additionalProperties': False,
        },
    },
    'required': ['quota_set'],
    'additionalProperties': False,
}
