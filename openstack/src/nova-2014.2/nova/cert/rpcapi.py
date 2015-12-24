# Copyright 2013, Red Hat, Inc.
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
Client side of the cert manager RPC API.
"""

from oslo.config import cfg
from oslo import messaging

from nova import rpc

rpcapi_opts = [
    cfg.StrOpt('cert_topic',
               default='cert',
               help='The topic cert nodes listen on'),
]

CONF = cfg.CONF
CONF.register_opts(rpcapi_opts)

rpcapi_cap_opt = cfg.StrOpt('cert',
        help='Set a version cap for messages sent to cert services')
CONF.register_opt(rpcapi_cap_opt, 'upgrade_levels')


class CertAPI(object):
    '''Client side of the cert rpc API.

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

    def __init__(self):
        super(CertAPI, self).__init__()
        target = messaging.Target(topic=CONF.cert_topic, version='2.0')
        version_cap = self.VERSION_ALIASES.get(CONF.upgrade_levels.cert,
                                               CONF.upgrade_levels.cert)
        self.client = rpc.get_client(target, version_cap=version_cap)

    def _get_compat_version(self, current, havana_compat):
        if not self.client.can_send_version(current):
            return havana_compat
        return current

    def revoke_certs_by_user(self, ctxt, user_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'revoke_certs_by_user', user_id=user_id)

    def revoke_certs_by_project(self, ctxt, project_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'revoke_certs_by_project',
                          project_id=project_id)

    def revoke_certs_by_user_and_project(self, ctxt, user_id, project_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'revoke_certs_by_user_and_project',
                          user_id=user_id, project_id=project_id)

    def generate_x509_cert(self, ctxt, user_id, project_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'generate_x509_cert',
                          user_id=user_id,
                          project_id=project_id)

    def fetch_ca(self, ctxt, project_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'fetch_ca', project_id=project_id)

    def fetch_crl(self, ctxt, project_id):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'fetch_crl', project_id=project_id)

    def decrypt_text(self, ctxt, project_id, text):
        # NOTE(russellb) Havana compat
        version = self._get_compat_version('2.0', '1.0')
        cctxt = self.client.prepare(version=version)
        return cctxt.call(ctxt, 'decrypt_text',
                          project_id=project_id,
                          text=text)
