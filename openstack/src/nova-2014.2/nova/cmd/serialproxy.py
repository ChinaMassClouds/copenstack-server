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

"""
Websocket proxy that is compatible with OpenStack Nova
Serial consoles. Leverages websockify.py by Joel Martin.
Based on nova-novncproxy.
"""

import os
import sys

from oslo.config import cfg

from nova import config
from nova.console import websocketproxy
from nova.openstack.common import log as logging
from nova.openstack.common.report import guru_meditation_report as gmr
from nova import version


opts = [
    cfg.StrOpt('serialproxy_host',
               default='0.0.0.0',
               help='Host on which to listen for incoming requests'),
    cfg.IntOpt('serialproxy_port',
               default=6083,
               help='Port on which to listen for incoming requests'),
    ]

CONF = cfg.CONF
CONF.register_cli_opts(opts, group="serial_console")
CONF.import_opt('debug', 'nova.openstack.common.log')
CONF.import_opt('record', 'nova.cmd.novnc')
CONF.import_opt('daemon', 'nova.cmd.novnc')
CONF.import_opt('ssl_only', 'nova.cmd.novnc')
CONF.import_opt('source_is_ipv6', 'nova.cmd.novnc')
CONF.import_opt('cert', 'nova.cmd.novnc')
CONF.import_opt('key', 'nova.cmd.novnc')


def exit_with_error(msg, errno=-1):
    print(msg) and sys.exit(errno)


def main():
    # Setup flags
    config.parse_args(sys.argv)

    if CONF.ssl_only and not os.path.exists(CONF.cert):
        exit_with_error("SSL only and %s not found" % CONF.cert)

    logging.setup("nova")
    gmr.TextGuruMeditation.setup_autorun(version)

    # Create and start the NovaWebSockets proxy
    server = websocketproxy.NovaWebSocketProxy(
        listen_host=CONF.serial_console.serialproxy_host,
        listen_port=CONF.serial_console.serialproxy_port,
        source_is_ipv6=CONF.source_is_ipv6,
        verbose=CONF.verbose,
        cert=CONF.cert,
        key=CONF.key,
        ssl_only=CONF.ssl_only,
        daemon=CONF.daemon,
        record=CONF.record,
        traffic=CONF.verbose and not CONF.daemon,
        file_only=True,
        RequestHandlerClass=websocketproxy.NovaProxyRequestHandler)
    server.start_server()
