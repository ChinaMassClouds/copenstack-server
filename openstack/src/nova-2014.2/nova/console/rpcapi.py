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
Client side of the console RPC API.
"""

from oslo.config import cfg
from oslo import messaging

from nova import rpc

rpcapi_opts = [
    cfg.StrOpt('console_topic',
               default='console',
               help='The topic console proxy nodes listen on'),
]

CONF = cfg.CONF
CONF.register_opts(rpcapi_opts)

rpcapi_cap_opt = cfg.StrOpt('console',
        help='Set a version cap for messages sent to console services')
CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


class ConsoleAPI(object):
    '''Client side of the console rpc API.

    API version history:

        1.0 - Initial version.
        1.1 - Added get_backdoor_port()

        ... Grizzly and Havana support message version 1.1.  So, any changes to
        existing methods in 1.x after that point should be done such that they
        can handle the version_cap being set to 1.1.

        2.0 - Major API rev for Icehouse

        ... Icehouse and Juno support message version 2.0.  So, any changes to
        existing methods in 2.x after that point should be done such that they
        can handle the version_cap being set to 2.0.
    '''

    VERSION_ALIASES = {
        'grizzly': '1.1',
        'havana': '1.1',
        'icehouse': '2.0',
        'juno': '2.0',
    }

    def __init__(self, topic=None, server=None):
        super(ConsoleAPI, self).__init__()
        topic = topic if topic else CONF.console_topic
        target = messaging.Target(topic=topic, server=server, version='2.0')
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.console,
                                               CONF.upgrade_levels.console)
        self.client = rpc.get_client(target, version_cap=version_cap)

    def _get_compat_version(self, current, havana_compat):
        if not self.client.can_send_version(current):
            return havana_compat
        return current

    def add_console(self, ctxt, instance_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        cctxt.cast(ctxt, 'add_console', instance_id=instance_id)

    def remove_console(self, ctxt, console_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        cctxt.cast(ctxt, 'remove_console', console_id=console_id)
