# Copyright (c) 2014 The Johns Hopkins University/Applied Physics Laboratory
# All Rights Reserved
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

import os

from nova.virt.libvirt import utils

_dmcrypt_suffix = '-dmcrypt'


def volume_name(base):
    """Returns the suffixed dmcrypt volume name.

    This is to avoid collisions with similarly named device mapper names for
    LVM volumes
    """
    return base + _dmcrypt_suffix


def is_encrypted(path):
    """Returns true if the path corresponds to an encrypted disk."""
    if path.startswith('/dev/mapper'):
        return path.rpartition('/')[2].endswith(_dmcrypt_suffix)
    else:
        return False


def create_volume(target, device, cipher, key_size, key):
    """Sets up a dmcrypt mapping

    :param target: device mapper logical device name
    :param device: underlying block device
    :param cipher: encryption cipher string digestible by cryptsetup
    :param key_size: encryption key size
    :param key: encryption key as an array of unsigned bytes
    """
    cmd = ('cryptsetup',
           'create',
           target,
           device,
           '--cipher=' + cipher,
           '--key-size=' + str(key_size),
           '--key-file=-')
    key = ''.join(map(lambda byte: "%02x" % byte, key))
    utils.execute(*cmd, process_input=key, run_as_root=True)


def delete_volume(target):
    """Deletes a dmcrypt mapping

    :param target: name of the mapped logical device
    """
    utils.execute('cryptsetup', 'remove', target, run_as_root=True)


def list_volumes():
    """Function enumerates encrypted volumes."""
    return [dmdev for dmdev in os.listdir('/dev/mapper')
            if dmdev.endswith('-dmcrypt')]
