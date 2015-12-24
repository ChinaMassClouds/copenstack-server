# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
Volume utilities for virt drivers.
"""

from nova import exception
from nova import utils


def get_iscsi_initiator():
    """Get iscsi initiator name for this machine."""
    # NOTE(vish) openiscsi stores initiator name in a file that
    #            needs root permission to read.
    try:
        contents = utils.read_file_as_root('/etc/iscsi/initiatorname.iscsi')
    except exception.FileNotFound:
        return None

    for l in contents.split('\n'):
        if l.startswith('InitiatorName='):
            return l[l.index('=') + 1:].strip()
