# Copyright 2013 Red Hat, Inc.
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

"""
Client side of the consoleauth RPC API.
"""

from oslo.config import cfg
from oslo import messaging

from nova import rpc

CONF = cfg.CONF

rpcapi_cap_opt = cfg.StrOpt('consoleauth',
        help='Set a version cap for messages sent to consoleauth services')
CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


class ConsoleAuthAPI(object):
    '''Client side of the consoleauth rpc API.

    API version history:

        * 1.0 - Initial version.
        * 1.1 - Added get_backdoor_port()
        * 1.2 - Added instance_uuid to authorize_console, and
                delete_tokens_for_instance

        ... Grizzly and Havana support message version 1.2.  So, any changes
        to existing methods in 2.x after that point should be done such that
        they can handle the version_cap being set to 1.2.

        * 2.0 - Major API rev for Icehouse

        ... Icehouse and Juno support message version 2.0.  So, any changes to
        existing methods in 2.x after that point should be done such that they
        can handle the version_cap being set to 2.0.
    '''

    VERSION_ALIASES = {
        'grizzly': '1.2',
        'havana': '1.2',
        'icehouse': '2.0',
        'juno': '2.0',
    }

    def __init__(self):
        super(ConsoleAuthAPI, self).__init__()
        target = messaging.Target(topic=CONF.consoleauth_topic, version='2.0')
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.consoleauth,
                                               CONF.upgrade_levels.consoleauth)
        self.client = rpc.get_client(target, version_cap=version_cap)

    def authorize_console(self, ctxt, token, console_type, host, port,
                          internal_access_path, instance_uuid):
        # The remote side doesn't return anything, but we want to block
        # until it completes.'
        version = '2.0'
        if not self.client.can_send_version('2.0'):
            # NOTE(russellb) Havana compat
            version = '1.2'
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt,
                          'authorize_console',
                          token=token, console_type=console_type,
                          host=host, port=port,
                          internal_access_path=internal_access_path,
                          instance_uuid=instance_uuid)

    def check_token(self, ctxt, token):
        version = '2.0'
        if not self.client.can_send_version('2.0'):
            # NOTE(russellb) Havana compat
            version = '1.0'
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'check_token', token=token)

    def delete_tokens_for_instance(self, ctxt, instance_uuid):
        version = '2.0'
        if not self.client.can_send_version('2.0'):
            # NOTE(russellb) Havana compat
            version = '1.2'
        cctxt = self.client.prepare(version=version)
        return cctxt.cast(ctxt,
                          'delete_tokens_for_instance',
                          instance_uuid=instance_uuid)
