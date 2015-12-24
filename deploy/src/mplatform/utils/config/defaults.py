#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# defaults.py - Copyright (C) 2012 Red Hat, Inc.
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
from mplatform.utils import base, exceptions, valid , config, log
from mplatform.utils.config.network import NicConfig
from mplatform.utils.exceptions import InvalidData
from mplatform.utils import storage, process, fs, AugeasWrapper, console, \
    system, firewall
from mplatform.utils.fs import Config, ShellVarFile, File
from mplatform.utils.network import NIC, Bridges, Bonds
from mplatform.utils.system import Bootloader
from mplatform.utils.node import utils
import glob
import os

"""
Classes and functions related to model of the configuration of mplatform.utils Node.

Node is writing it's configuration into one central configuration file
(mplatform.utils_NODE_DEFAULTS_FILENAME) afterwards all actual configurations files are
created based on this file. This module provides an high level to this model.

There are classes for all components which can be configured through that
central configuration file.
Each class (for a component) can have a configure and apply_config method. Look
at the NodeConfigFileSection for more informations.

Each class should implement a configure method, mainly to define all the
required arguments (or keys).
"""

LOGGER = log.getLogger(__name__)

#mplatform.utils_NODE_DEFAULTS_FILENAME = "/etc/default/mplatform.utils"


def exists():
    pass
    """Determin if the defaults file exists
    """
    #return os.path.exists(mplatform.utils_NODE_DEFAULTS_FILENAME)


class NodeConfigFile(ShellVarFile):
    """NodeConfigFile is a specififc interface to some configuration file
    with a specififc syntax
    """
    def __init__(self, filename=None):
        filename = filename
        #filename = filename or mplatform.utils_NODE_DEFAULTS_FILENAME
        #if filename == mplatform.utils_NODE_DEFAULTS_FILENAME \
        #   and not fs.File(filename).exists():
        #    raise RuntimeError("Node config file does not exist: %s" %
        #                       filename)
        #super(NodeConfigFile, self).__init__(filename, create=True)


class NodeConfigFileSection(base.Base):
    none_value = None
    keys = []
    raw_file = None

    def __init__(self, filename=None):
        super(NodeConfigFileSection, self).__init__()
        self.raw_file = NodeConfigFile(filename)

    def update(self, *args, **kwargs):
        """This function set's the correct entries in the defaults file for
        that specififc subclass.
        Is expected to be decorated by _map_config_and_update_defaults()
        """
        raise NotImplementedError

    def transaction(self):
        """This method returns a transaction which needs to be performed
        to activate the defaults config (so e.g. update cfg files and restart
        services).

        This can be used to update the UI when the transaction has many steps
        """
        raise NotImplementedError

    def commit(self, *args, **kwargs):
        """Shotcut to run the transaction associtated with the class

        A shortcut for:
        tx = obj.transaction(pw="foo")
        tx()
        """
        tx = self.transaction(*args, **kwargs)
        return tx()

    def _args_to_keys_mapping(self, keys_to_args=False):
        """Map the named arguments of th eupdate() method to the CFG keys

        Returns:
            A dict mapping an argname to it's cfg key (or vice versa)
        """
        func = self.update.wrapped_func
        # co_varnames contains all args within the func, the args are kept
        # at the beginning of the list, that's why we slice the varnames list
        # (start after self until the number of args)
        argnames = func.func_code.co_varnames[1:func.func_code.co_argcount]
        assert len(argnames) == len(self.keys), "argnames (%s) != keys (%s)" %\
            (argnames, self.keys)
        mapping = zip(self.keys, argnames) if keys_to_args else zip(argnames,
                                                                    self.keys)
        return dict(mapping)

    def retrieve(self):
        """Returns the config keys of the current component

        Returns:
            A dict with a mapping (arg, value).
            arg corresponds to the named arguments of the subclass's
            configure() method.
        """
        keys_to_args = self._args_to_keys_mapping(keys_to_args=True)
        cfg = self.raw_file.get_dict()
        model = {}
        for key in self.keys:
            value = cfg[key] if key in cfg else self.none_value
            model[keys_to_args[key]] = value
        assert len(keys_to_args) == len(model)
        return model

    def clear(self, keys=None):
        """Remove the configuration for this item
        """
        keys = keys or self.keys
        cfg = self.raw_file.get_dict()
        to_be_deleted = dict((k, None) for k in keys)
        cfg.update(to_be_deleted)
        self.raw_file.update(cfg, remove_empty=True)

    def _map_config_and_update_defaults(self, *args, **kwargs):
        assert len(args) == 0
        assert (set(self.keys) ^ set(kwargs.keys())) == set(), \
            "Keys: %s, Args: %s" % (self.keys, kwargs)
        new_dict = dict((k.upper(), v) for k, v in kwargs.items())
        self.raw_file.update(new_dict, remove_empty=True)

        # Returning self allows chaining for decorated functions
        return self

    @staticmethod
    def map_and_update_defaults_decorator(func):
        """
        FIXME Use some kind of map to map between args and env_Vars
              this would alsoallow kwargs

        >>> class Foo(object):
        ...     keys = None
        ...     def _map_config_and_update_defaults(self, *args, **kwargs):
        ...         return kwargs
        ...     @NodeConfigFileSection.map_and_update_defaults_decorator
        ...     def meth(self, a, b, c):
        ...         assert type(a) is int
        ...         assert type(b) is int
        ...         return {"mplatform.utils_C": "c%s" % c}
        >>> foo = Foo()
        >>> foo.keys = ("mplatform.utils_A", "mplatform.utils_B", "mplatform.utils_C")
        >>> foo.meth(1, 2, 3)
        {'mplatform.utils_A': 1, 'mplatform.utils_B': 2, 'mplatform.utils_C': 'c3'}
        """
        def wrapper(self, *args, **kwargs):
            if kwargs:
                # if kwargs are given it is interpreted as an update
                # so existing values which are not given in the kwargs are kept
                arg_to_key = self._args_to_keys_mapping()
                update_kwargs = self.retrieve()
                update_kwargs.update(dict((k, v) for k, v in kwargs.items()
                                          if k in update_kwargs.keys()))
                kwargs = update_kwargs
                new_cfg = dict((arg_to_key[k], v) for k, v
                               in update_kwargs.items())
            else:
                if len(self.keys) != len(args):
                    raise Exception("There are not enough arguments given " +
                                    "for %s of %s" % (func, self))
                new_cfg = dict(zip(self.keys, args))
            custom_cfg = func(self, *args, **kwargs) or {}
            assert type(custom_cfg) is dict, "%s must return a dict" % func
            new_cfg.update(custom_cfg)
            return self._map_config_and_update_defaults(**new_cfg)
        wrapper.wrapped_func = func
        return wrapper


class ConfigVersion(NodeConfigFileSection):
    """Keep the mplatform.utils-node version in the config for which this config is
    intended
    """
    keys = ("mplatform.utils_CONFIG_VERSION", )

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, ver):
        pass

    def set_to_current(self):
        curver = system.node_version()
        self.logger.debug("Setting config version to: %s" % curver)
        self.update(curver)


class Network(NodeConfigFileSection):
    """Sets network stuff
    - mplatform.utils_BOOTIF
    - mplatform.utils_IP_ADDRESS, mplatform.utils_IP_NETMASK, mplatform.utils_IP_GATEWAY
    - mplatform.utils_VLAN

    >>> from mplatform.utils.node.utils import fs
    >>> n = Network(fs.FakeFs.File("dst"))
    >>> _ = n.update("eth0", None, "10.0.0.1", "255.0.0.0", "10.0.0.255",
    ...          "20")
    >>> data = sorted(n.retrieve().items())
    >>> data[:3]
    [('bootproto', None), ('gateway', '10.0.0.255'), ('iface', 'eth0')]
    >>> data[3:]
    [('ipaddr', '10.0.0.1'), ('netmask', '255.0.0.0'), ('vlanid', '20')]

    >>> n.clear()
    >>> data = sorted(n.retrieve().items())
    >>> data[:3]
    [('bootproto', None), ('gateway', None), ('iface', None)]
    >>> data[3:]
    [('ipaddr', None), ('netmask', None), ('vlanid', None)]
    """
    keys = ("mplatform.utils_BOOTIF",
            "mplatform.utils_BOOTPROTO",
            "mplatform.utils_IP_ADDRESS",
            "mplatform.utils_IP_NETMASK",
            "mplatform.utils_IP_GATEWAY",
            "mplatform.utils_VLAN")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, iface, bootproto, ipaddr=None, netmask=None, gateway=None,
               vlanid=None):
        if bootproto not in ["dhcp", None]:
            raise exceptions.InvalidData("Unknown bootprotocol: %s" %
                                         bootproto)
        (valid.IPv4Address() | valid.Empty(or_none=True))(ipaddr)
        (valid.IPv4Address() | valid.Empty(or_none=True))(netmask)
        (valid.IPv4Address() | valid.Empty(or_none=True))(gateway)

    def configure_no_networking(self, iface=None):
        """Can be used to disable all networking
        """
        # iface = iface or self.retrieve()["iface"]
        # name = iface + "-DISABLED"
        # FIXME why should we use ifname-DISABLED here?
        self.update(None, None, None, None, None, None)

    def configure_dhcp(self, iface, vlanid=None):
        """Can be used to configure NIC iface on the vlan vlanid with DHCP
        """
        self.update(iface, "dhcp", None, None, None, vlanid)

    def configure_static(self, iface, ipaddr, netmask, gateway, vlanid):
        """Can be used to configure a static IP on a NIC
        """
        self.update(iface, None, ipaddr, netmask, gateway, vlanid)

    def transaction(self):
        """Return all transactions to re-configure networking
        """
        services = ["network", "ntpd", "ntpdate", "rpcbind", "nfslock",
                    "rpcidmapd", "nfs-idmapd", "rpcgssd"]

        def do_services(cmd, services):
            with console.CaptureOutput():
                for name in services:
                    system.service(name, cmd, False)

        class StopNetworkServices(utils.Transaction.Element):
            title = "Stop network services"

            def commit(self):
                do_services("stop", services)

        class RemoveConfiguration(utils.Transaction.Element):
            title = "Remove existing configuration"

            def commit(self):
                self._remove_devices()
                self._remove_ifcfg_configs()

            def _remove_devices(self):
                process.call(["killall", "dhclient"])

                vlans = utils.network.Vlans()
                vifs = vlans.all_vlan_devices()
                self.logger.debug("Attempting to delete all vlans: %s" % vifs)
                for vifname in vifs:
                    vlans.delete(vifname)
                    if NicConfig(vifname).exists():
                        NicConfig(vifname).delete()

                # FIXME we are removing ALL bridges
                bridges = Bridges()
                for bifname in bridges.ifnames():
                    bridges.delete(bifname)
                    if NicConfig(bifname).exists():
                        NicConfig(bifname).delete()

                bonds = Bonds()
                if bonds.is_enabled():
                    bonds.delete_all()

            def _remove_ifcfg_configs(self):
                pat = NicConfig.IfcfgBackend.filename_tpl % "*"
                remaining_ifcfgs = glob.glob(pat)
                self.logger.debug("Attemtping to remove remaining ifcfgs: %s" %
                                  remaining_ifcfgs)
                pcfg = fs.Config()
                for fn in remaining_ifcfgs:
                    pcfg.delete(fn)

        class WriteConfiguration(utils.Transaction.Element):
            title = "Write new configuration"

            def commit(self):
                m = Network().retrieve()
                aug = AugeasWrapper()

                needs_networking = False

                bond = NicBonding().retrieve()
                if bond["slaves"]:
                    NicBonding().transaction().commit()
                    needs_networking = True

                if m["iface"]:
                    self.__write_config()
                    needs_networking = True

                self.__write_lo()

                aug.set("/files/etc/sysconfig/network/NETWORKING",
                        "yes" if needs_networking else "no")

                fs.Config().persist("/etc/sysconfig/network")
                fs.Config().persist("/etc/hosts")

            def __write_config(self):
                m = Network().retrieve()

                topology = NetworkLayout().retrieve()["layout"]
                with_bridge = (topology == "bridged")

                mbond = NicBonding().retrieve()

                bridge_ifname = "br%s" % m["iface"]
                vlan_ifname = "%s.%s" % (m["iface"], m["vlanid"])

                nic_cfg = NicConfig(m["iface"])
                nic_cfg.device = m["iface"]
                nic_cfg.onboot = "yes"
                nic_cfg.nm_controlled = "no"

                # Only assign a hwaddr if it's not a bond
                if mbond["name"] != m["iface"]:
                    nic_cfg.hwaddr = NIC(m["iface"]).hwaddr

                if m["vlanid"]:
                    # Add a tagged interface
                    vlan_cfg = NicConfig(vlan_ifname)
                    vlan_cfg.device = vlan_ifname
                    vlan_cfg.vlan = "yes"
                    vlan_cfg.onboot = "yes"
                    vlan_cfg.nm_controlled = "no"
                    if with_bridge:
                        vlan_cfg.bridge = bridge_ifname
                    else:
                        self.__assign_ip_config(vlan_cfg)
                    vlan_cfg.save()
                else:
                    if with_bridge:
                        nic_cfg.bridge = bridge_ifname
                    else:
                        # No vlan and no bridge: So assign IP to NIC
                        self.__assign_ip_config(nic_cfg)

                if with_bridge:
                    # Add a bridge
                    bridge_cfg = NicConfig(bridge_ifname)
                    self.__assign_ip_config(bridge_cfg)
                    bridge_cfg.device = bridge_ifname
                    bridge_cfg.delay = "0"
                    bridge_cfg.type = "Bridge"
                    bridge_cfg.nm_controlled = "no"
                    bridge_cfg.save()

                nic_cfg.save()

            def __write_lo(self):
                cfg = NicConfig("lo")
                cfg.device = "lo"
                cfg.ipaddr = "127.0.0.1"
                cfg.netmask = "255.0.0.0"
                cfg.onboot = "yes"
                cfg.save()

            def __assign_ip_config(self, cfg):
                m = Network().retrieve()
                m_dns = Nameservers().retrieve()
                m_ipv6 = IPv6().retrieve()

                cfg.bootproto = m["bootproto"]
                cfg.ipaddr = m["ipaddr"] or None
                cfg.gateway = m["gateway"] or None
                cfg.netmask = m["netmask"] or None
                cfg.onboot = "yes"
                cfg.peerntp = "yes"

                if m_dns["servers"]:
                    cfg.peerdns = "no"

                if m_ipv6["bootproto"]:
                    cfg.ipv6init = "yes"
                    cfg.ipv6forwarding = "no"
                    cfg.ipv6_autoconf = "no"
                else:
                    cfg.ipv6init = "no"
                    cfg.ipv6_autoconf = "no"

                if m_ipv6["bootproto"] == "auto":
                    cfg.ipv6_autoconf = "yes"
                elif m_ipv6["bootproto"] == "dhcp":
                    cfg.dhcpv6c = "yes"
                elif m_ipv6["bootproto"] == "static":
                    cfg.ipv6addr = "%s/%s" % (m_ipv6["ipaddr"],
                                              m_ipv6["netmask"])
                    cfg.ipv6_defaultgw = m_ipv6["gateway"]

        class PersistMacNicMapping(utils.Transaction.Element):
            title = "Persist MAC-NIC Mappings"

            def commit(self):
                # Copy the initial net rules to a file that get's not
                # overwritten at each boot, rhbz#773495
                rulesfile = "/etc/udev/rules.d/70-persistent-net.rules"
                newrulesfile = "/etc/udev/rules.d/71-persistent-node-net.rules"
                if File(rulesfile).exists():
                    process.check_call(["cp", rulesfile, newrulesfile])
                    fs.Config().persist(newrulesfile)

        class StartNetworkServices(utils.Transaction.Element):
            title = "Start network services"

            def commit(self):
                do_services("start", services)
                utils.AugeasWrapper.force_reload()
                utils.network.reset_resolver()

        tx = utils.Transaction("Applying new network configuration")
        tx.append(StopNetworkServices())
        tx.append(RemoveConfiguration())
        tx.append(WriteConfiguration())
        if system.is_max_el(6):
            # Running EL6 -- persist network renaming
            tx.append(PersistMacNicMapping())
        tx.append(StartNetworkServices())
        return tx


class NicBonding(NodeConfigFileSection):
    """Create a bonding device
    - mplatform.utils_BOND

    >>> from mplatform.utils.node.utils import fs
    >>> n = NicBonding(fs.FakeFs.File("dst"))
    >>> _ = n.update("bond0", ["ens1", "ens2", "ens3"], "mode=4")
    >>> data = sorted(n.retrieve().items())
    >>> data[:2]
    [('name', 'bond0'), ('options', 'mode=4')]
    >>> data [2:]
    [('slaves', ['ens1', 'ens2', 'ens3'])]
    """
    keys = ("mplatform.utils_BOND_NAME",
            "mplatform.utils_BOND_SLAVES",
            "mplatform.utils_BOND_OPTIONS")

    # Set some sane defaults if not options are diven
    # https://git.kernel.org/cgit/linux/kernel/git/torvalds/linux.git/
    # tree/Documentation/networking/bonding.txt#n153
    default_options = "mode=balance-rr miimon=100"

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, name, slaves, options):
        if name is not None and not name.startswith("bond"):
            raise InvalidData("Bond ifname must start with 'bond'")
        if slaves is not None and type(slaves) is not list:
            raise InvalidData("Slaves must be a list")

        options = options or self.default_options
        return {"mplatform.utils_BOND_SLAVES": ",".join(slaves) if slaves else None,
                "mplatform.utils_BOND_OPTIONS": options if name else None}

    def retrieve(self):
        cfg = super(NicBonding, self).retrieve()
        cfg.update({"slaves": (cfg["slaves"].split(",") if cfg["slaves"]
                               else [])})
        return cfg

    def configure_no_bond(self):
        """Remove all bonding
        """
        return self.update(None, None, None)

    def configure_8023ad(self, name, slaves):
        return self.update(name, slaves, "mode=4")

    def transaction(self):
        bond = NicBonding().retrieve()
        if not bond["options"]:
            bond["options"] = self.default_options

        class RemoveConfigs(utils.Transaction.Element):
            title = "Clean potential bond configurations"

            def commit(self):
                net = Network()
                mnet = net.retrieve()
                if mnet["iface"] and mnet["iface"].startswith("bond"):
                    net.configure_no_networking()

                for ifname in NicConfig.list():
                    cfg = NicConfig(ifname)
                    if cfg.master:
                        self.logger.debug("Removing master from %s" % ifname)
                        cfg.master = None
                        cfg.slave = None
                        cfg.save()
                    elif ifname.startswith("bond"):
                        self.logger.debug("Removing master %s" % ifname)
                        cfg.delete()

                Bonds().delete_all()

        class WriteSlaveConfigs(utils.Transaction.Element):
            title = "Writing bond slaves configuration"

            def commit(self):
                m = Network().retrieve()
                if m["iface"] in bond["slaves"]:
                    raise RuntimeError("Bond slave can not be used as " +
                                       "primary device")

                for slave in bond["slaves"]:
                    slave_cfg = NicConfig(slave)
                    slave_cfg.hwaddr = NIC(slave).hwaddr
                    slave_cfg.device = slave
                    slave_cfg.slave = "yes"
                    slave_cfg.master = bond["name"]
                    slave_cfg.onboot = "yes"
                    slave_cfg.nm_controlled = "no"
                    slave_cfg.save()

        class WriteMasterConfig(utils.Transaction.Element):
            title = "Writing bond master configuration"

            def commit(self):
                if bond["options"]:
                    cfg = NicConfig(bond["name"])
                    cfg.device = bond["name"]
                    cfg.onboot = "yes"
                    cfg.nm_controlled = "no"
                    cfg.type = "Bond"
                    cfg.bonding_opts = bond["options"]

                    cfg.save()

        tx = utils.Transaction("Writing bond configuration")
        if bond["slaves"]:
            tx.append(WriteMasterConfig())
            tx.append(WriteSlaveConfigs())
        else:
            tx.append(RemoveConfigs())
        return tx


class NetworkLayout(NodeConfigFileSection):
    """Sets the network topology
    - mplatform.utils_NETWORK_TOPOLOGY

    >>> from mplatform.utils.node.utils import fs
    >>> n = NetworkLayout(fs.FakeFs.File("dst"))
    >>> _ = n.update("bridged")
    >>> sorted(n.retrieve().items())
    [('layout', 'bridged')]
    """
    keys = ("mplatform.utils_NETWORK_LAYOUT",)

    # The BOOTIF NIC is configured directly
    LAYOUT_DIRECT = "direct"

    # bridged way, a bridge is created for BOOTIF
    LAYOUT_BRIDGED = "bridged"

    known_layouts = [LAYOUT_DIRECT,
                     LAYOUT_BRIDGED]

    default_layout = LAYOUT_DIRECT

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, layout=None):
        assert layout in self.known_layouts + [None]

    def configure_bridged(self):
        return self.update("bridged")

    def configure_direct(self):
        return self.update("direct")

    def configure_default(self):
        return self.update(None)


class IPv6(NodeConfigFileSection):
    """Sets IPv6 network stuff
    - mplatform.utils_IPV6 (static, auto, dhcp)
    - mplatform.utils_IPV6_ADDRESS
    - mplatform.utils_IPV6_NETMASK
    - mplatform.utils_IPV6_GATEWAY

    >>> from mplatform.utils.node.utils import fs
    >>> n = IPv6(fs.FakeFs.File("dst"))
    >>> _ = n.update("auto", "11::22", "42", "11::44")
    >>> data = sorted(n.retrieve().items())
    >>> data[0:3]
    [('bootproto', 'auto'), ('gateway', '11::44'), ('ipaddr', '11::22')]
    >>> data[3:]
    [('netmask', '42')]
    """
    keys = ("mplatform.utils_IPV6",
            "mplatform.utils_IPV6_ADDRESS",
            "mplatform.utils_IPV6_NETMASK",
            "mplatform.utils_IPV6_GATEWAY")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, bootproto, ipaddr, netmask, gateway):
        if bootproto not in ["auto", "static", "none", "dhcp", None]:
            raise exceptions.InvalidData("Unknown bootprotocol: %s" %
                                         bootproto)
        (valid.IPv6Address() | valid.Empty(or_none=True))(ipaddr)
        (valid.Number(bounds=[0, 128]) | valid.Empty(or_none=True))(netmask)
        (valid.IPv6Address() | valid.Empty(or_none=True))(gateway)

    def transaction(self):
        return self.__legacy_transaction()

    def __legacy_transaction(self):
        """The transaction is the same as in the Network class - using the
        legacy stuff.
        This should be rewritten to allow a more fine grained progress
        monitoring.
        """
        tx = Network().transaction()
        return tx

    def disable(self):
        """Can be used to disable IPv6
        """
        self.update(None, None, None, None)

    def configure_dhcp(self):
        """Can be used to configure NIC iface on the vlan vlanid with DHCP
        """
        self.update("dhcp", None, None, None)

    def configure_static(self, address, netmask, gateway):
        """Can be used to configure a static IPv6 IP on a NIC
        """
        self.update("static", address, netmask, gateway)

    def configure_auto(self):
        """Can be used to autoconfigure IPv6 on a NIC
        """
        self.update("auto", None, None, None)


class Hostname(NodeConfigFileSection):
    """Configure hostname


    >>> from mplatform.utils.node.utils import fs
    >>> n = Hostname(fs.FakeFs.File("dst"))
    >>> hostname = "host.example.com"
    >>> _ = n.update(hostname)
    >>> n.retrieve()
    {'hostname': 'host.example.com'}
    """
    keys = ("mplatform.utils_HOSTNAME",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, hostname):
        (valid.Empty() | valid.HostnameLength())(hostname)

    def transaction(self):
        cfg = self.retrieve()
        hostname = cfg["hostname"]

        class UpdateHostname(utils.Transaction.Element):
            title = "Setting hostname"

            def __init__(self, hostname):
                self.hostname = hostname

            def commit(self):
                aug = AugeasWrapper()

                localhost_entry = None
                for entry in aug.match("/files/etc/hosts/*"):
                    if aug.get(entry + "/ipaddr") == "127.0.0.1":
                        localhost_entry = entry
                        break

                if not localhost_entry:
                    raise RuntimeError("Couldn't find entry for localhost")

                # Remove all aliases
                for alias_entry in aug.match(localhost_entry + "/alias"):
                    aug.remove(alias_entry, False)

                # ... and create a new one
                aliases = ["localhost", "localhost.localdomain"]
                if self.hostname:
                    aliases.append(self.hostname)

                for _idx, alias in enumerate(aliases):
                    idx = _idx + 1
                    p = "%s/alias[%s]" % (localhost_entry, idx)
                    aug.set(p, alias, False)

                config.network.hostname(self.hostname)

                fs.Config().persist("/etc/hosts")
                fs.Config().persist("/etc/hostname")
                fs.Config().persist("/etc/sysconfig/network")

                utils.network.reset_resolver()

        tx = utils.Transaction("Configuring hostname")
        tx.append(UpdateHostname(hostname))
        return tx

    def configure_hostname(self, hostname):
        """Configure the hostname of this system
        Args:
            hostname: Hostname to be set
        """
        return self.update(hostname)


class Nameservers(NodeConfigFileSection):
    """Configure nameservers

    >>> from mplatform.utils.node.utils import fs
    >>> n = Nameservers(fs.FakeFs.File("dst"))
    >>> servers = ["10.0.0.2", "10.0.0.3"]
    >>> _ = n.update(servers)
    >>> data = n.retrieve()
    >>> all([servers[idx] == s for idx, s in enumerate(data["servers"])])
    True
    >>> _ = n.update([])
    >>> n.retrieve()
    {'servers': None}
    """
    keys = ("mplatform.utils_DNS",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, servers):
        assert type(servers) is list
        # Preparation
        servers = [i.strip() for i in servers]
        servers = [i for i in servers if i not in ["", None]]

        # Validation
        validator = lambda v: valid.FQDNOrIPAddress()
        map(validator, servers)

        # Mangling for the conf file format
        return {"mplatform.utils_DNS": ",".join(servers) or None
                }

    def configure(self, servers):
        self.update(servers)

    def retrieve(self):
        """We mangle the original vale a bit for py convenience
        """
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"servers": cfg["servers"].split(",") if cfg["servers"]
                    else None
                    })
        return cfg

    def transaction(self):
        """Derives the nameserver config from mplatform.utils_DNS

        1. Parse nameservers from defaults
        2. Update resolv.conf
        3. Update ifcfg- (peerdns=no if manual resolv.conf)
        4. Persist resolv.conf

        Args:
            servers: List of servers (str)
        """
        aug = utils.node.utils.AugeasWrapper()
        m = Nameservers().retrieve()

        tx = utils.Transaction("Configuring DNS")

        servers = []
        if m["servers"]:
            servers = m["servers"]
        else:
            self.logger.debug("No DNS server entry in default config")

        class UpdateResolvConf(utils.Transaction.Element):
            title = "Updating resolv.conf"

            def commit(self):
                # Write resolv.conf any way, sometimes without servers
                comment = ("Please make changes through the TUI " +
                           "or management server. " +
                           "Manual edits to this file will be " +
                           "lost on reboot")
                aug.set("/files/etc/resolv.conf/#comment[1]", comment)
                # Now set the nameservers
                config.network.nameservers(servers)
                utils.fs.Config().persist("/etc/resolv.conf")

                utils.network.reset_resolver()

        class UpdatePeerDNS(utils.Transaction.Element):
            title = "Update PEERDNS statement in ifcfg-* files"

            def commit(self):
                # Set or remove PEERDNS for all ifcfg-*
                for nic in glob.glob("/etc/sysconfig/network-scripts/ifcfg-*"):
                    if "ifcfg-lo" in nic:
                        continue
                    path = "/files%s/PEERDNS" % nic
                    if len(servers) > 0:
                        aug.set(path, "no")
                    else:
                        aug.remove(path)

        # FIXME what about restarting NICs to pickup peerdns?

        tx += [UpdateResolvConf(), UpdatePeerDNS()]

        return tx


class Timeservers(NodeConfigFileSection):
    """Configure timeservers

    >>> from mplatform.utils.node.utils import fs
    >>> n = Timeservers(fs.FakeFs.File("dst"))
    >>> servers = ["10.0.0.4", "10.0.0.5", "0.example.com"]
    >>> _ = n.update(servers)
    >>> data = n.retrieve()
    >>> all([servers[idx] == s for idx, s in enumerate(data["servers"])])
    True
    >>> _ = n.update([])
    >>> n.retrieve()
    {'servers': None}
    """
    keys = ("mplatform.utils_NTP",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, servers):
        assert type(servers) is list
        # Preparation
        servers = [i.strip() for i in servers]
        servers = [i for i in servers if i not in ["", None]]

        # Validation
        validator = lambda v: valid.FQDNOrIPAddress()
        map(validator, servers)

        # Mangling to match the conf file
        return {"mplatform.utils_NTP": ",".join(servers) or None
                }

    def configure(self, servers):
        self.update(servers)

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"servers": cfg["servers"].split(",") if cfg["servers"]
                    else None
                    })
        return cfg

    def transaction(self):
        m = Timeservers().retrieve()

        servers = m["servers"]

        class WriteConfiguration(utils.Transaction.Element):
            title = "Writing timeserver configuration"

            def commit(self):
                aug = AugeasWrapper()

                p = "/files/etc/ntp.conf"
                aug.remove(p, False)
                aug.set(p + "/driftfile", "/var/lib/ntp/drift", False)
                aug.set(p + "/includefile", "/etc/ntp/crypto/pw", False)
                aug.set(p + "/keys", "/etc/ntp/keys", False)
                aug.save()

                config.network.timeservers(servers)

                utils.fs.Config().persist("/etc/ntp.conf")

        class ApplyConfiguration(utils.Transaction.Element):
            title = "Restarting time services"

            def commit(self):
                system.service("ntpd", "stop", False)
                system.service("ntpdate", "start", False)
                system.service("ntpd", "start", False)

        tx = utils.Transaction("Configuring timeservers")
        tx.append(WriteConfiguration())
        tx.append(ApplyConfiguration())
        return tx

    @staticmethod
    def filter_valid_servers(servers):
        # Call .validate() directly so we don't throw an exception and
        # can just filter with booleans
        return [x for x in servers if valid.FQDNOrIPAddress().validate(x)]


class Syslog(NodeConfigFileSection):
    """Configure rsyslog


    >>> from mplatform.utils.node.utils import fs
    >>> n = Syslog(fs.FakeFs.File("dst"))
    >>> server = "10.0.0.6"
    >>> port = "514"
    >>> _ = n.update(server, port)
    >>> sorted(n.retrieve().items())
    [('port', '514'), ('server', '10.0.0.6')]
    """
    keys = ("mplatform.utils_SYSLOG_SERVER",
            "mplatform.utils_SYSLOG_PORT")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, server, port):
        (valid.Empty(or_none=True) | valid.FQDNOrIPAddress())(server)
        valid.Port()(port)

    def configure(self, server, port=None):
        self.update(server, port)

    def transaction(self):
        return self.__legacy_transaction()

    def __legacy_transaction(self):
        cfg = dict(self.retrieve())
        server, port = (cfg["server"], cfg["port"])

        class CreateRsyslogConfig(utils.Transaction.Element):
            title = "Setting syslog server and port"

            def commit(self):
                import mplatform.utilsnode.log as olog
                olog.mplatform.utils_rsyslog(server, port, "udp")

        tx = utils.Transaction("Configuring syslog")
        tx.append(CreateRsyslogConfig())
        return tx


class Collectd(NodeConfigFileSection):
    """Configure collectd

    >>> from mplatform.utils.node.utils import fs
    >>> n = Collectd(fs.FakeFs.File("dst"))
    >>> server = "10.0.0.7"
    >>> port = "42"
    >>> _ = n.update(server, port)
    >>> sorted(n.retrieve().items())
    [('port', '42'), ('server', '10.0.0.7')]
    """
    keys = ("mplatform.utils_COLLECTD_SERVER",
            "mplatform.utils_COLLECTD_PORT")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, server, port):
        valid.FQDNOrIPAddress()(server)
        valid.Port()(port)

    def configure(self, server, port):
        self.update(server, port)

    def transaction(self):
        return self.__legacy_transaction()

    def __legacy_transaction(self):
        cfg = dict(self.retrieve())
        server, port = (cfg["server"], cfg["port"])

        class ConfigureCollectd(utils.Transaction.Element):
            title = "Setting collect server and port"

            def commit(self):
                pass
                # pylint: disable-msg=E0611
                #from mplatform.ovirt_config_setup import collectd  # @UnresolvedImport
                # pylint: enable-msg=E0611
                #if collectd.write_collectd_config(server, port):
               #     Config().persist("/etc/collectd.conf")
               #     self.logger.debug("Collectd was configured successfully")
                #else:
                #    raise exceptions.TransactionError("Failed to configure " +
                #                                      "collectd")

        tx = utils.Transaction("Configuring collectd")
        #tx.append(ConfigureCollectd())
        return tx


class KDump(NodeConfigFileSection):
    """Configure kdump

    >>> from mplatform.utils.node.utils import fs
    >>> n = KDump(fs.FakeFs.File("dst"))
    >>> nfs_url = "host.example.com:/dst/path"
    >>> ssh_url = "root@host.example.com"
    >>> ssh_key = "http://example.com/id_rsa"
    >>> _ = n.update(nfs_url, ssh_url, ssh_key, True)
    >>> d = sorted(n.retrieve().items())
    >>> d[:2]
    [('local', True), ('nfs', 'host.example.com:/dst/path')]
    >>> d[2:]
    [('ssh', 'root@host.example.com'), \
('ssh_key', 'http://example.com/id_rsa')]
    """
    keys = ("mplatform.utils_KDUMP_NFS",
            "mplatform.utils_KDUMP_SSH",
            "mplatform.utils_KDUMP_SSH_KEY",
            "mplatform.utils_KDUMP_LOCAL")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, nfs, ssh, ssh_key, local):
        (valid.Empty(or_none=True) | valid.NFSAddress())(nfs)
        (valid.Empty(or_none=True) | valid.SSHAddress())(ssh)
        (valid.Empty(or_none=True) | valid.URL())(ssh_key)
        (valid.Empty(or_none=True) | valid.Boolean())(local)
        return {"mplatform.utils_KDUMP_LOCAL": "true" if local else None
                }

    def configure_nfs(self, nfs_location):
        self.update(nfs_location, None, None, None)

    def configure_ssh(self, ssh_location, ssh_key=None):
        self.update(None, ssh_location, ssh_key, None)

    def configure_local(self):
        self.update(None, None, None, True)

    def configure_disable(self):
        self.update(None, None, None, None)

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"local": True if cfg["local"] == "true" else None
                    })
        return cfg

    def transaction(self):
        cfg = dict(self.retrieve())
        nfs, ssh, ssh_key, local = (cfg["nfs"], cfg["ssh"], cfg["ssh_key"],
                                    cfg["local"])

        aug = AugeasWrapper()
        prefix = "/files/etc/kdump.conf/"
        nfs_path = "/var/run/kdump-nfs"

        def _set_values(vals):
            for k, v in vals.iteritems():
                aug.set(prefix + k, v)
            aug.save()

        class BackupKdumpConfig(utils.Transaction.Element):
            title = "Backing up config files"

            def __init__(self):
                self.backups = utils.fs.BackupedFiles(["/etc/kdump.conf"])
                super(BackupKdumpConfig, self).__init__()

            def commit(self):
                self.backups.create(ignore_existing=True)

        class WipeKdumpConfig(utils.Transaction.Element):
            title = "Removing set kdump options"

            def commit(self):
                paths = ["default", "ext4", "path", "nfs", "ssh", "net"]

                vals = aug.get_many(paths, basepath=prefix)
                [aug.remove(v) for v in vals.keys() if vals[v] is not None]
                aug.save()

        class LocalKdumpConfig(utils.Transaction.Element):
            title = "Setting local kdump config"

            def commit(self):
                vals = {"default": "reboot",
                        "ext4": "/dev/HostVG/Data",
                        "path": "core"}

                # kdumpctl on EL7 doesn't like it if the path doesn't
                # exist
                if not os.path.isdir(os.path.join("/data", vals["path"])):
                        os.makedirs(os.path.join("/data", vals["path"]))

                _set_values(vals)

        class MountNFS(utils.Transaction.Element):
            title = "Mounting NFS volume for kdump configuration"

            def commit(self):
                try:
                    if not os.path.isdir(nfs_path):
                        os.makedirs(nfs_path)
                    system.Mount(nfs_path, nfs, "nfs").mount()

                    File("/etc/fstab").write(
                        "\n%s\t%s\tnfs\tdefaults\t0 0" % (nfs, nfs_path),
                        "a")
                    Config().persist("/etc/fstab")
                except utils.process.CalledProcessError:
                    self.logger.warning("Failed to mount %s at " +
                                        "%s" % (nfs, nfs_path),
                                        exc_info=True)

        class UmountNFS(utils.Transaction.Element):
            title = "Umounting Kdump NFS volume"

            def commit(self):
                try:
                    system.Mount(nfs_path).umount()
                    File("/etc/fstab").sed(r'\#.*{dir}#d'.format(
                        dir=nfs_path))
                except utils.process.CalledProcessError:
                    self.logger.warning("Failed to umount %s" % nfs,
                                        exc_info=True)

        class CreateNfsKdumpConfig(utils.Transaction.Element):
            title = "Creating kdump NFS config"

            def commit(self):
                vals = {"default": "reboot",
                        "nfs": nfs}

                _set_values(vals)

        class PopulateSshKeys(utils.Transaction.Element):
            title = "Fetching and testing SSH keys"

            def commit(self):
                import pycurl
                import cStringIO
                from shutil import copy2

                buf = cStringIO.StringIO()

                curl = pycurl.Curl()
                curl.setopt(curl.URL, ssh_key)
                curl.setopt(curl.WRITEFUNCTION, buf.write)
                curl.setopt(curl.FAILONERROR, True)
                try:
                    curl.perform()
                except pycurl.error, error:
                    errno, err_str = error
                    self.logger.warning("Failed to fetch SSH key: %s" %
                                        err_str)

                os.mkdir("/tmp/kdump-ssh")
                os.chmod("/tmp/kdump-ssh", 0600)
                with open("/tmp/kdump-ssh/id", "w") as f:
                    f.write(buf.getvalue())
                os.chmod("/tmp/kdump-ssh/id", 0600)

                try:
                    cmd = ['ssh', '-o', 'BatchMode=yes', '-i',
                           '/tmp/kdump-ssh/id', ssh, 'true']
                    utils.process.check_call(cmd)
                    copy2("/tmp/kdump-ssh/id", "/root/.ssh/kdump_id_rsa")
                except utils.process.CalledProcessError as e:
                    self.logger.warning("Failed to authenticate using SSH "
                                        "key: %s" % e)

        class CreateSshKdumpConfig(utils.Transaction.Element):
            title = "Creating kdump SSH config"

            def commit(self):
                vals = {"default": "reboot",
                        "net": ssh}

                _set_values(vals)

                kdumpctl_cmd = system.which("kdumpctl")
                if kdumpctl_cmd:
                    cmd = [kdumpctl_cmd, "propagate"]
                else:
                    cmd = ["service", "kdump", "propagate"]

                try:
                    utils.process.check_call(cmd)

                    conf = Config()
                    files = ["/root/.ssh/kdump_id_rsa.pub",
                             "/root/.ssh/kdump_id_rsa",
                             "/root/.ssh/known_hosts",
                             "/root/.ssh/config"]

                    [conf.persist(f) for f in files]

                except utils.process.CalledProcessError as e:
                    self.logger.warning("Failed to activate KDump with " +
                                        "SSH: %s" % e)

        class RemoveKdumpConfig(utils.Transaction.Element):
            title = "Removing kdump backup"

            def __init__(self, backups):
                self.backups = backups
                super(RemoveKdumpConfig, self).__init__()

            def commit(self):
                Config().unpersist("/etc/kdump.conf")
                system.service("kdump", "stop")
                fs.File('/etc/kdump.conf').touch()

                self.backups.remove()

        class RestartKdumpService(utils.Transaction.Element):
            title = "Restarting kdump service"

            def __init__(self, backups):
                self.backups = backups
                super(RestartKdumpService, self).__init__()

            def commit(self):
                from mplatform.utils.node.ovirtfunctions import unmount_config

                try:
                    if system.which("kdumpctl"):
                        with open("/dev/null", "wb") as DEVNULL:
                            utils.process.check_call(["kdumpctl", "restart"],
                                                     stdout=DEVNULL,
                                                     stderr=DEVNULL)
                    else:
                        system.service("kdump", "restart")
                except utils.process.CalledProcessError as e:
                    self.logger.info("Failure while restarting kdump: %s" % e)
                    unmount_config("/etc/kdump.conf")
                    self.backups.restore("/etc/kdump.conf")
                    system.service("kdump", "restart", do_raise=False)

                    raise RuntimeError("KDump configuration failed, " +
                                       "location unreachable. Previous " +
                                       "configuration was restored.")

                Config().persist("/etc/kdump.conf")
                self.backups.remove()

        tx = utils.Transaction("Configuring kdump")

        backup_txe = BackupKdumpConfig()
        tx.append(backup_txe)

        wipe_txe = WipeKdumpConfig()
        tx.append(wipe_txe)

        final_txe = RestartKdumpService(backup_txe.backups)
        if nfs:
            if not system.is_max_el(6):
                tx.append(MountNFS())
            tx.append(CreateNfsKdumpConfig())
        elif ssh:
            if ssh_key:
                tx.append(PopulateSshKeys())
            tx.append(CreateSshKdumpConfig())
        elif local in [True, False]:
            tx.append(LocalKdumpConfig())
        else:
            final_txe = RemoveKdumpConfig(backup_txe.backups)

        if not nfs and os.path.ismount(nfs_path):
            tx.insert(0, UmountNFS())

        tx.append(final_txe)

        return tx


class iSCSI(NodeConfigFileSection):
    """Configure iSCSI

    >>> from mplatform.utils.node.utils import fs
    >>> n = iSCSI(fs.FakeFs.File("dst"))
    >>> _ = n.update("iqn.1992-01.com.example:node",
    ...          "iqn.1992-01.com.example:target", "10.0.0.8", "42")
    >>> data = sorted(n.retrieve().items())
    >>> data[:2]
    [('name', 'iqn.1992-01.com.example:node'), ('target_host', '10.0.0.8')]
    >>> data[2:]
    [('target_name', 'iqn.1992-01.com.example:target'), ('target_port', '42')]
    """
    keys = ("mplatform.utils_ISCSI_NODE_NAME",
            "mplatform.utils_ISCSI_TARGET_NAME",
            "mplatform.utils_ISCSI_TARGET_IP",
            "mplatform.utils_ISCSI_TARGET_PORT")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, name, target_name, target_host, target_port):
        # FIXME add more validation
        valid.IQN()(name)
        (valid.Empty(or_none=True) | valid.IQN())(target_name)
        (valid.Empty(or_none=True) | valid.FQDNOrIPAddress())(target_host)
        (valid.Empty(or_none=True) | valid.Port())(target_port)

    def configure_initiator_name(self, name):
        self.update(name, None, None, None)

    def transaction(self):
        cfg = dict(self.retrieve())
        initiator_name = cfg["name"]

        class ConfigureIscsiInitiator(utils.Transaction.Element):
            title = "Setting the iSCSI initiator name"

            def commit(self):
                iscsi =utils.storage.iSCSI()
                iscsi.initiator_name(initiator_name)

        tx = utils.Transaction("Configuring the iSCSI Initiator")
        tx.append(ConfigureIscsiInitiator())
        return tx


class SCSIDhAlua(NodeConfigFileSection):
    """Configure scsi_dh_alua

    >>> from mplatform.utils.node.utils import fs
    >>> n = SCSIDhAlua(fs.FakeFs.File("dst"))
    >>> enabled = True
    >>> _ = n.update(enabled)
    >>> n.retrieve().items()
    [('enabled', True)]
    """
    keys = ("mplatform.utils_SCSI_DH_ALUA",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, enabled):
        (valid.Boolean() | valid.Empty(or_none=True))(enabled)
        return {"mplatform.utils_SCSI_DH_ALUA": "true" if enabled else None}

    def configure(self, enabled):
        self.update(enabled)

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"enabled": True if cfg["enabled"] == "true" else False})
        return cfg

    def transaction(self):
        cfg = dict(self.retrieve())
        enabled = cfg["enabled"]

        class CreateSCSIConfig(utils.Transaction.Element):
            title = "Setting scsi_dh_alua"

            def commit(self):
                if enabled:
                    Bootloader().Arguments()["rdloaddriver"] = "scsi_dh_alua"
                else:
                    del Bootloader().Arguments()["rdloaddriver"]

        tx = utils.Transaction("Configuring scsi_dh_alua")
        tx.append(CreateSCSIConfig())
        return tx


class Netconsole(NodeConfigFileSection):
    """Configure netconsole

    >>> from mplatform.utils.node.utils import fs
    >>> n = Netconsole(fs.FakeFs.File("dst"))
    >>> server = "10.0.0.9"
    >>> port = "666"
    >>> _ = n.update(server, port)
    >>> sorted(n.retrieve().items())
    [('port', '666'), ('server', '10.0.0.9')]
    """
    keys = ("mplatform.utils_NETCONSOLE_SERVER",
            "mplatform.utils_NETCONSOLE_PORT")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, server, port):
        (valid.Empty(or_none=True) | valid.FQDNOrIPAddress())(server)
        valid.Port()(port)

    def configure(self, server, port):
        self.update(server, port)

    def transaction(self):
        def _clear_config():
            self.logger.info("Disabling netconsole")
            f = File("/etc/sysconfig/netconsole")
            f.sed("/SYSLOGADDR/d")
            f.sed("/SYSLOGPORT/d")

        def configure_netconsole(server, port):
            aug = utils.AugeasWrapper()
            if server and port:
                aug.set("/files/etc/sysconfig/netconsole/SYSLOGADDR",
                        server)
                aug.set("/files/etc/sysconfig/netconsole/SYSLOGPORT",
                        port)
                try:
                    system.service("netconsole", "restart")
                except:
                    _clear_config()
                    raise RuntimeError("Failed to restart netconsole "
                                       "service. Is the host resolvable?")
            else:
                _clear_config()
            fs.Config().persist("/etc/sysconfig/netconsole")
            self.logger.info("Netconsole Configuration Updated")

        cfg = dict(self.retrieve())
        server, port = (cfg["server"], cfg["port"])

        class CreateNetconsoleConfig(utils.Transaction.Element):
            if server:
                title = "Setting netconsole server and port"
            else:
                title = "Disabling netconsole"

            def commit(self):
                configure_netconsole(server, port or "6666")

        tx = utils.Transaction("Configuring netconsole")
        tx.append(CreateNetconsoleConfig())
        return tx


class Logrotate(NodeConfigFileSection):
    """Configure logrotate

    >>> from mplatform.utils.node.utils import fs
    >>> n = Logrotate(fs.FakeFs.File("dst"))
    >>> max_size = "42"
    >>> _ = n.update(max_size, None)
    >>> n.retrieve().items()
    [('interval', 'daily'), ('max_size', '42')]
    >>> interval = "weekly"
    >>> _ = n.update(max_size, interval)
    >>> n.retrieve().items()
    [('interval', 'weekly'), ('max_size', '42')]
    """

    # FIXME this key is new!
    keys = ("mplatform.utils_LOGROTATE_MAX_SIZE", "mplatform.utils_LOGROTATE_INTERVAL")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, max_size, interval):
        valid.Number([0, None])(max_size)
        if interval not in ["daily", "weekly", "monthly", None]:
            raise InvalidData("Update interval must be a valid logrotate "
                              "schedule period or None")

        return {"mplatform.utils_LOGROTATE_MAX_SIZE": max_size,
                "mplatform.utils_LOGROTATE_INTERVAL": "daily" if interval is None
                else interval}

    def configure_interval(self, interval):
        self.update(None, interval)

    def configure_max_size(self, max_size):
        self.update(max_size, None)

    def transaction(self):
        cfg = dict(self.retrieve())
        max_size = cfg["max_size"] or 1024
        interval = cfg["interval"] or "daily"

        class CreateLogrotateConfig(utils.Transaction.Element):
            title = "Setting logrotate maximum logfile size"

            def commit(self):
                aug = utils.AugeasWrapper()
                aug.set("/files/etc/logrotate.d/mplatform.utils-node/rule/minsize",
                        max_size)
                Config().persist("/etc/logrotate.d/mplatform.utils-node")

        class SetLogrotateInterval(utils.Transaction.Element):
            title = "Setting logrotate interval"

            def commit(self):
                aug = utils.AugeasWrapper()
                aug.set("/files/etc/logrotate.d/mplatform.utils-node/rule/schedule",
                        interval)
                Config().persist("/etc/logrotate.d/mplatform.utils-node")

        tx = utils.Transaction("Configuring logrotate")

        tx.append(CreateLogrotateConfig())
        tx.append(SetLogrotateInterval())
        return tx


class Keyboard(NodeConfigFileSection):
    """Configure keyboard

    >>> from mplatform.utils.node.utils import fs
    >>> n = Keyboard(fs.FakeFs.File("dst"))
    >>> layout = "de_DE.UTF-8"
    >>> _ = n.update(layout)
    >>> n.retrieve()
    {'layout': 'de_DE.UTF-8'}
    """
    # FIXME this key is new!
    keys = ("mplatform.utils_KEYBOARD_LAYOUT",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, layout):
        # FIXME Some validation that layout is in the list of available layouts
        pass

    def configure(self, layout):
        self.update(layout)

    def transaction(self):
        cfg = dict(self.retrieve())
        layout = cfg["layout"]

        class CreateKeyboardConfig(utils.Transaction.Element):
            title = "Setting keyboard layout"

            def commit(self):
                kbd = utils.system.Keyboard()
                kbd.set_layout(layout)
                conf = Config()
                conf.persist("/etc/vconsole.conf")
                conf.persist("/etc/sysconfig/keyboard")

        tx = utils.Transaction("Configuring keyboard layout")
        tx.append(CreateKeyboardConfig())
        return tx


class NFSv4(NodeConfigFileSection):
    """Configure NFSv4

    >>> from mplatform.utils.node.utils import fs
    >>> n = NFSv4(fs.FakeFs.File("dst"))
    >>> domain = "foo.example"
    >>> _ = n.update(domain)
    >>> n.retrieve().items()
    [('domain', 'foo.example')]
    """
    # FIXME this key is new!
    keys = ("mplatform.utils_NFSV4_DOMAIN",)

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, domain):
        (valid.Empty() | valid.FQDN())(domain)
        return {"mplatform.utils_NFSV4_DOMAIN": domain or None
                }

    def configure_domain(self, domain):
        self.update(domain)

    def transaction(self):
        cfg = dict(self.retrieve())
        domain = cfg["domain"]

        class ConfigureNfsv4(utils.Transaction.Element):
            title = "Setting NFSv4 domain"

            def commit(self):
                nfsv4 = storage.NFSv4()

                # Need to pass "" to disable Domain line
                nfsv4.domain(domain or "")

                fs.Config().persist(nfsv4.configfilename)
                servicename = "rpcidmapd"
                sysdfile = File("/usr/lib/systemd/system/nfs-idmapd.service")
                if sysdfile.exists():
                    servicename = "nfs-idmapd"
                system.service(servicename, "restart")
                process.call(["nfsidmap", "-c"])

        tx = utils.Transaction("Configuring NFSv4")
        tx.append(ConfigureNfsv4())
        return tx


class SSH(NodeConfigFileSection):
    """Configure SSH

    >>> from mplatform.utils.node.utils import fs
    >>> n = SSH(fs.FakeFs.File("dst"))
    >>> pwauth = True
    >>> num_bytes = "24"
    >>> disable_aesni = True
    >>> port = '2222'
    >>> _ = n.update(pwauth, port, num_bytes, disable_aesni)
    >>> sorted(n.retrieve().items())
    [('disable_aesni', True), ('num_bytes', '24'),\
 ('port', '2222'), ('pwauth', True)]
    """
    keys = ("mplatform.utils_SSH_PWAUTH",
            "mplatform.utils_SSH_PORT",
            "mplatform.utils_USE_STRONG_RNG",
            "mplatform.utils_DISABLE_AES_NI")

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, pwauth, port, num_bytes, disable_aesni):
        valid.Boolean()(pwauth)
        (valid.Number() | valid.Empty(or_none=True))(port)
        (valid.Number() | valid.Empty(or_none=True))(num_bytes)
        (valid.Boolean() | valid.Empty(or_none=True))(disable_aesni)
        return {"mplatform.utils_SSH_PWAUTH": "yes" if pwauth else None,
                "mplatform.utils_SSH_PORT": port if port else "22",
                "mplatform.utils_DISABLE_AES_NI": "true" if disable_aesni else None
                }

    def configure_aesni(self, enabled):
        self.update(None, None, None, enabled)

    def configure_pwauth(self, enabled):
        self.update(enabled, None, None, None)

    def configure_port(self, port):
        self.update(None, port, None, None)

    def configure_aesni_bytes(self, num_bytes):
        self.update(None, None, num_bytes, None)

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"pwauth": True if cfg["pwauth"] == "yes" else False,
                    "disable_aesni": True if cfg["disable_aesni"] == "true"
                    else False
                    })
        return cfg

    def transaction(self):
        cfg = dict(self.retrieve())
        pwauth, port, num_bytes, disable_aesni = (cfg["pwauth"],
                                                  cfg["port"],
                                                  cfg["num_bytes"],
                                                  cfg["disable_aesni"])

        ssh = utils.security.Ssh()

        class ConfigurePasswordAuthentication(utils.Transaction.Element):
            title = "Configuring SSH password authentication"

            def commit(self):
                ssh.password_authentication(pwauth)

        class ConfigureSSHPort(utils.Transaction.Element):
            title = "Configuring SSH port"

            def commit(self):
                ssh.port(port)
                firewall.open_port(port, "tcp")

        class ConfigureStrongRNG(utils.Transaction.Element):
            title = "Configuring SSH strong RNG"

            def commit(self):
                ssh.strong_rng(num_bytes)

        class ConfigureAESNI(utils.Transaction.Element):
            title = "Configuring SSH AES NI"

            def commit(self):
                ssh.disable_aesni(disable_aesni)

        class PersistConfig(utils.Transaction.Element):
            title = "Persisting configuration"

            def commit(self):
                fs.Config().persist("/etc/ssh/sshd_config")
                fs.Config().persist("/etc/profile")

        tx = utils.Transaction("Configuring SSH")
        tx.append(ConfigurePasswordAuthentication())
        tx.append(ConfigureSSHPort())
        tx.append(ConfigureStrongRNG())
        tx.append(ConfigureAESNI())
        tx.append(PersistConfig())
        return tx


class Installation(NodeConfigFileSection):
    """Configure storage
    This is a class to handle the storage parameters used at installation time

    >>> from mplatform.utils.node.utils import fs
    >>> n = Installation(fs.FakeFs.File("dst"))
    >>> kwargs = {"init": ["/dev/sda"], "root_install": "1"}
    >>> _ = n.update(**kwargs)
    >>> data = n.retrieve().items()
    """
    keys = ("mplatform.utils_INIT",
            "mplatform.utils_OVERCOMMIT",
            "mplatform.utils_VOL_ROOT_SIZE",
            "mplatform.utils_VOL_EFI_SIZE",
            "mplatform.utils_VOL_SWAP_SIZE",
            "mplatform.utils_VOL_LOGGING_SIZE",
            "mplatform.utils_VOL_CONFIG_SIZE",
            "mplatform.utils_VOL_DATA_SIZE",
            "mplatform.utils_INSTALL",
            "mplatform.utils_UPGRADE",
            "mplatform.utils_INSTALL_ROOT",
            "mplatform.utils_ROOT_INSTALL",
            "mplatform.utils_ISCSI_INSTALL"
            )

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, init, overcommit, root_size, efi_size,
               swap_size, logging_size, config_size, data_size, install,
               upgrade, install_root, root_install, iscsi_install):
        # FIXME no checking!
        return {"mplatform.utils_INIT": ",".join(init),
                "mplatform.utils_INSTALL_ROOT": "y" if install_root else None,
                "mplatform.utils_ROOT_INSTALL": "y" if root_install else None,
                "mplatform.utils_INSTALL": "1" if install else None,
                "mplatform.utils_UPGRADE": "1" if upgrade else None,
                "mplatform.utils_ISCSI_INSTALL": "1" if iscsi_install else None}

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg.update({"init": cfg["init"].split(",") if cfg["init"] else [],
                    "install_root": cfg["install_root"] == "y",
                    "root_install": cfg["root_install"] == "y",
                    "install": cfg["install"] == "1",
                    "iscsi_install": cfg["iscsi_install"] == "1",
                    "upgrade": cfg["upgrade"] == "1"})
        return cfg

    def transaction(self):
        return None

    def install_on(self, init, root_size, efi_size, swap_size, logging_size,
                   config_size, data_size):
        """Convenience function which can be used to set the parameters which
        are going to be picked up by the installer backend to install Node on
        the given storage with the given othere params
        """
        self.update(install=True,
                    install_root=True,
                    root_install=True,
                    init=init,
                    root_size=root_size,
                    efi_size=efi_size,
                    swap_size=swap_size,
                    logging_size=logging_size,
                    config_size=config_size,
                    data_size=data_size)

    def upgrade(self):
        """Convenience function setting the params to upgrade
        """
        self.update(upgrade=True,
                    install=None)


class Management(NodeConfigFileSection):
    """Exchange informations with management part

    Plugins can use this class as follows:

    from mplatform.utils.node.config.defaults import Management
    mgmt.update("mplatform.utils Engine at <url>",
                ["mplatform.utilsmgmt"],
                [])


    Keys
    ----
    MANAGED_BY=<descriptive-text>
        This key is used to (a) signal the Node is being managed and
        (b) signaling who is managing this node.
        The value can be a descriptive text inclduning e.g. an URL to point
        to the management instance.

    MANAGED_IFNAMES=<ifname>[,<ifname>,...]
        This key is used to specify a number (comma separated list) if
        ifnames which are managed and for which the TUI shall display some
        information (IP, ...).
        This can also be used by the TUI to decide to not offer NIC
        configuration to the user.
        This is needed to tell the TUI the _important_ NICs on this host.
        E.g. it's probably worth to provide the ifname of the management
        interface here, e.g mplatform.utilsmgmt.

    MANAGED_LOCKED_PAGES=<pagename>[,<pagename>,...]
        (Future) A list of pages which shall be locked e.g. because the
        management instance is configuring the aspect (e.g. networking or
        logging).
    """
    keys = ("MANAGED_BY",
            "MANAGED_IFNAMES",
            "MANAGED_LOCKED_PAGES"
            )

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, managed_by, managed_ifnames, managed_locked_pages):
        assert type(managed_ifnames) is list
        return {"MANAGED_IFNAMES": (",".join(managed_ifnames)
                                    if managed_ifnames else None)}

    def retrieve(self):
        cfg = dict(NodeConfigFileSection.retrieve(self))
        cfg["managed_ifnames"] = (cfg["managed_ifnames"].split(",")
                                  if cfg["managed_ifnames"] else None)
        return cfg

    def transaction(self):
        return None

    def is_managed(self):
        return True if self.retrieve()["managed_by"] else False

    def has_managed_ifnames(self):
        return True if self.retrieve()["managed_ifnames"] else False


class RuntimeImageState(NodeConfigFileSection):
    """Track informations about the image state
    """
    keys = ("RUNTIME_IMAGE_FINGERPRINT_LAST"
            )

    product_nvr = str(system.ProductInformation())

    @NodeConfigFileSection.map_and_update_defaults_decorator
    def update(self, fingerprint):
        pass

    def stored(self):
        """Return the stored fingerprint
        """
        return self.retrieve()["fingerprint"]

    def is_different(self):
        """Determin if the current runtime image is different
        compared to the last time the config file was updated
        """
        return self.stored() != self.product_nvr

    def test_and_set(self):
        """Check if the image state changed, and update to current

        Returns:
            True - if the state of the image changed (new image)
        """
        current = self.product_nvr
        is_different = self.is_different()

        if is_different:
            self.update(current)

        return is_different
