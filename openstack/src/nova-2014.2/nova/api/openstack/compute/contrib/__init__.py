# Copyright 2011 Justin Santa Barbara
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

"""Contrib contains extensions that are shipped with nova.

It can't be called 'extensions' because that causes namespacing problems.

"""

from oslo.config import cfg

from nova.api.openstack import extensions
from nova.openstack.common import log as logging

ext_opts = [
    cfg.ListOpt('osapi_compute_ext_list',
                default=[],
                help='Specify list of extensions to load when using osapi_'
                     'compute_extension option with nova.api.openstack.'
                     'compute.contrib.select_extensions'),
]
CONF = cfg.CONF
CONF.register_opts(ext_opts)

LOG = logging.getLogger(__name__)


def standard_extensions(ext_mgr):
    extensions.load_standard_extensions(ext_mgr, LOG, __path__, __package__)


def select_extensions(ext_mgr):
    extensions.load_standard_extensions(ext_mgr, LOG, __path__, __package__,
                                        CONF.osapi_compute_ext_list)
