# Copyright 2012 Red Hat, Inc.
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

import sys

from oslo.config import cfg

from nova.i18n import _
from nova.openstack.common import importutils
from nova.openstack.common import log as logging

driver_opts = [
    cfg.StrOpt('network_driver',
               default='nova.network.linux_net',
               help='Driver to use for network creation'),
]
CONF = cfg.CONF
CONF.register_opts(driver_opts)

LOG = logging.getLogger(__name__)


def load_network_driver(network_driver=None):
    if not network_driver:
        network_driver = CONF.network_driver

    if not network_driver:
        LOG.error(_("Network driver option required, but not specified"))
        sys.exit(1)

    LOG.info(_("Loading network driver '%s'") % network_driver)

    return importutils.import_module(network_driver)
