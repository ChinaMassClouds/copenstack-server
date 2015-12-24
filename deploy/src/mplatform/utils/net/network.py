#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# network.py - Copyright (C) 2012 Red Hat, Inc.
# Written by Fabian Deutsch <fabiand@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.  A copy of the GNU General Public License is
# also available at http://www.gnu.org/copyleft/gpl.html.

import glob
import gudev
import os.path
import re
import socket
import struct
import shlex
from django.utils import log
from mplatform.utils import process
from mplatform.utils import fs

"""
Some convenience functions related to networking
"""

LOGGER = log.getLogger(__name__)

#
# Try to use NM if available
# FIXME we need to migrte to GUdev at some poit to make it really work
#
_nm_client = None
try:
    # pylint: disable-msg=E0611
    from gi.repository import NetworkManager, NMClient  # @UnresolvedImport
    # pylint: enable-msg=E0611
    NetworkManager
    _nm_client = NMClient.Client.new()
    LOGGER.debug("NetworkManager support via GI (fast-path)")
except Exception as e:
    LOGGER.debug("NetworkManager support disabled: " +
                 "NM Client not found (%s)" % e)


class UnknownNicError(Exception):
    pass


def _query_udev_ifaces():
    client = gudev.Client(['net'])
    devices = client.query_by_subsystem("net")
    return [d.get_property("INTERFACE") for d in devices]


def _nm_ifaces():
    return [d.get_iface() for d in _nm_client.get_devices()]


def is_nm_managed(iface):
    """Wether an intreface is managed by NM or not (if it's running)
    """
    return _nm_client and iface in _nm_ifaces()


def all_ifaces():
    """A list of all network interfaces discovered by udev

    Returns:
        A list of all returned ifaces (names)
    """
    return _query_udev_ifaces()


class UdevNICInfo():
    """Gather NIC infos form udev
    """
    _client = gudev.Client(['net'])
    _cached_device = None

    ifname = None

    def __init__(self, iface):
        self.ifname = iface

    @property
    def _udev_device(self):
        if not self._cached_device:
            for d in self._client.query_by_subsystem("net"):
                if d.get_property("INTERFACE") == self.ifname:
                    self._cached_device = d

        if not self._cached_device:
            self.logger.debug("udev has no infos for %s" % self.ifname)

        return self._cached_device

    def __get_property(self, name):
        return self._udev_device.get_property(name) if self.exists() \
            else None

    def exists(self):
        return self._udev_device is not None

    @property
    def name(self):
        return self.__get_property("INTERFACE")

    @property
    def vendor(self):
        vendor = self.__get_property("ID_VENDOR_FROM_DATABASE")
        if not vendor:
            # fallback method for older udev versions
            try:
                dpath = self.__get_property("DEVPATH")
                pci_addr = dpath.split("/")[-3]
                cmd = ["lspci", "-m", "-s", pci_addr]
                lspci_out = process.pipe(cmd, check=True)
                # shelx needs str not unicode
                vendor = shlex.split(str(lspci_out))[2]
            except:
                LOGGER.debug("Failed to fetch vendor name for %s" % dpath,
                                  exc_info=True)
        return vendor

    @property
    def devtype(self):
        return self.__get_property("DEVTYPE")

    @property
    def devpath(self):
        return self.__get_property("DEVPATH")


class SysfsNICInfo():
    """Gather NIC infos fom sysfs
    """
    ifname = None

    def __init__(self, ifname):
        self.ifname = ifname

    def exists(self):
        return os.path.exists("/sys/class/net/%s" % self.ifname)

    @property
    def driver(self):
        driver_symlink = "/sys/class/net/%s/device/driver" % self.ifname
        driver = "unknown"
        if os.path.islink(driver_symlink):
            try:
                driver = os.path.basename(os.readlink(driver_symlink))
            except Exception as e:
                self.logger.warning(("Exception %s while reading driver " +
                                     "of '%s' from '%s'") % (e, self.ifname,
                                                             driver_symlink))
        return driver

    @property
    def hwaddr(self):
        hwaddr = None
        if self.exists():
            hwfilename = "/sys/class/net/%s/address" % self.ifname
            hwaddr = fs.get_contents(hwfilename).strip()
        return hwaddr

    @property
    def systype(self):
        systype = "ethernet"

        if self.is_vlan():
            # Check if vlan
            systype = "vlan"

        elif self.is_bridge():
            # Check if bridge
            systype = "bridge"

        return systype

    def is_vlan(self):
        return len(glob.glob("/proc/net/vlan/%s" % self.ifname)) > 0

    def is_bridge(self):
        return os.path.exists("/sys/class/net/%s/bridge" % self.ifname)


class NIC():
    """Offers an API tp common NIC related functions is also a model for any
    logical NIC.
    """
    ifname = None
    vendor = None
    driver = None
    hwaddr = None
    typ = None
    config = None

    def __init__(self, ifname):
        self.ifname = ifname

        self._udevinfo = UdevNICInfo(self.ifname)
        self.vendor = self._udevinfo.vendor

        self._sysfsinfo = SysfsNICInfo(self.ifname)
        self.driver = self._sysfsinfo.driver
        self.hwaddr = self._sysfsinfo.hwaddr

        self.typ = self._udevinfo.devtype or self._sysfsinfo.systype

    def exists(self):
        """If this NIC currently exists in the system

        """
        return self.ifname in all_ifaces()

    def is_configured(self):
        """If there is a configuration for this NIC
        """
        ipv4_configured = self.config.bootproto or self.config.ipaddr
        ipv6_configured = (self.config.dhcpv6c or self.config.ipv6_autoconf or
                           self.config.ipv6addr)
        return ipv4_configured or ipv6_configured


    def ipv4_address(self):
        return self.ip_addresses(["inet"])["inet"]

    def ipv6_address(self):
        return self.ip_addresses(["inet6"])["inet6"]








