# Copyright (c) 2011 OpenStack Foundation
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

from nova import utils

ipv6_backend_opt = cfg.StrOpt('ipv6_backend',
                              default='rfc2462',
                              help='Backend to use for IPv6 generation')

CONF = cfg.CONF
CONF.register_opt(ipv6_backend_opt)
IMPL = None


def reset_backend():
    global IMPL
    IMPL = utils.LazyPluggable('ipv6_backend',
               rfc2462='nova.ipv6.rfc2462',
               account_identifier='nova.ipv6.account_identifier')


def to_global(prefix, mac, project_id):
    return IMPL.to_global(prefix, mac, project_id)


def to_mac(ipv6_address):
    return IMPL.to_mac(ipv6_address)


reset_backend()
