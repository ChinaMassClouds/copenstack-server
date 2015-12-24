#!/usr/bin/python
#
# Project Chost
#
# Copyright IBM, Corp. 2014
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301  USA

# This module contains functions that the manipulate
# and configure the Nginx proxy.

import os
import pwd
import subprocess
from string import Template

from config import paths


def _create_proxy_config(host, port, proxy_port, path):

    config_dir = paths.conf_dir
    # No certificates specified by the user

    # Read template file and create a new config file
    # with the specified parameters.
    with open(os.path.join(config_dir, "nginx.conf.in")) as template:
        data = template.read()
    data = Template(data)
    data = data.safe_substitute(host=host,
                                port=port,
                                proxy_port=proxy_port,
                                path=path)

    # Write file to be used for nginx.
    config_file = open(os.path.join(config_dir, "nginx_mplatform.conf"), "w")
    config_file.write(data)
    config_file.close()


def start_proxy(options):
    """Start nginx reverse proxy."""
    _create_proxy_config(options.host, options.port, options.proxy_port, options.path)
    config_dir = paths.conf_dir
    config_file = "%s/nginx_mplatform.conf" % config_dir
    cmd = ['nginx', '-c', config_file]
    subprocess.call(cmd)


def terminate_proxy():
    """Stop nginx process."""
    term_proxy_cmd = ['nginx', '-s', 'stop']
    subprocess.call(term_proxy_cmd)
