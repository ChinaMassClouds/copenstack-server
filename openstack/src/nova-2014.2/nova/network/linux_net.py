# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""Implements vlans, bridges, and iptables rules using linux utilities."""

import calendar
import inspect
import os
import re

import netaddr
from oslo.config import cfg
import six

from nova import exception
from nova.i18n import _
from nova import objects
from nova.openstack.common import excutils
from nova.openstack.common import fileutils
from nova.openstack.common import importutils
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging
from nova.openstack.common import processutils
from nova.openstack.common import timeutils
from nova import paths
from nova import utils

LOG = logging.getLogger(__name__)


linux_net_opts = [
    cfg.MultiStrOpt('dhcpbridge_flagfile',
                    default=['/etc/nova/nova-dhcpbridge.conf'],
                    help='Location of flagfiles for dhcpbridge'),
    cfg.StrOpt('networks_path',
               default=paths.state_path_def('networks'),
               help='Location to keep network config files'),
    cfg.StrOpt('public_interface',
               default='eth0',
               help='Interface for public IP addresses'),
    cfg.StrOpt('dhcpbridge',
               default=paths.bindir_def('nova-dhcpbridge'),
               help='Location of nova-dhcpbridge'),
    cfg.StrOpt('routing_source_ip',
               default='$my_ip',
               help='Public IP of network host'),
    cfg.IntOpt('dhcp_lease_time',
               default=86400,
               help='Lifetime of a DHCP lease in seconds'),
    cfg.MultiStrOpt('dns_server',
                    default=[],
                    help='If set, uses specific DNS server for dnsmasq. Can'
                         ' be specified multiple times.'),
    cfg.BoolOpt('use_network_dns_servers',
                default=False,
                help='If set, uses the dns1 and dns2 from the network ref.'
                     ' as dns servers.'),
    cfg.ListOpt('dmz_cidr',
               default=[],
               help='A list of dmz range that should be accepted'),
    cfg.MultiStrOpt('force_snat_range',
               default=[],
               help='Traffic to this range will always be snatted to the '
                    'fallback ip, even if it would normally be bridged out '
                    'of the node. Can be specified multiple times.'),
    cfg.StrOpt('dnsmasq_config_file',
               default='',
               help='Override the default dnsmasq settings with this file'),
    cfg.StrOpt('linuxnet_interface_driver',
               default='nova.network.linux_net.LinuxBridgeInterfaceDriver',
               help='Driver used to create ethernet devices.'),
    cfg.StrOpt('linuxnet_ovs_integration_bridge',
               default='br-int',
               help='Name of Open vSwitch bridge used with linuxnet'),
    cfg.BoolOpt('send_arp_for_ha',
                default=False,
                help='Send gratuitous ARPs for HA setup'),
    cfg.IntOpt('send_arp_for_ha_count',
               default=3,
               help='Send this many gratuitous ARPs for HA setup'),
    cfg.BoolOpt('use_single_default_gateway',
                default=False,
                help='Use single default gateway. Only first nic of vm will '
                     'get default gateway from dhcp server'),
    cfg.MultiStrOpt('forward_bridge_interface',
                    default=['all'],
                    help='An interface that bridges can forward to. If this '
                         'is set to all then all traffic will be forwarded. '
                         'Can be specified multiple times.'),
    cfg.StrOpt('metadata_host',
               default='$my_ip',
               help='The IP address for the metadata API server'),
    cfg.IntOpt('metadata_port',
               default=8775,
               help='The port for the metadata API port'),
    cfg.StrOpt('iptables_top_regex',
               default='',
               help='Regular expression to match iptables rule that should '
                    'always be on the top.'),
    cfg.StrOpt('iptables_bottom_regex',
               default='',
               help='Regular expression to match iptables rule that should '
                    'always be on the bottom.'),
    cfg.StrOpt('iptables_drop_action',
               default='DROP',
               help=('The table that iptables to jump to when a packet is '
                     'to be dropped.')),
    cfg.IntOpt('ovs_vsctl_timeout',
               default=120,
               help='Amount of time, in seconds, that ovs_vsctl should wait '
                    'for a response from the database. 0 is to wait forever.'),
    cfg.BoolOpt('fake_network',
                default=False,
                help='If passed, use fake network devices and addresses'),
    ]

CONF = cfg.CONF
CONF.register_opts(linux_net_opts)
CONF.import_opt('host', 'nova.netconf')
CONF.import_opt('use_ipv6', 'nova.netconf')
CONF.import_opt('my_ip', 'nova.netconf')
CONF.import_opt('network_device_mtu', 'nova.objects.network')


# NOTE(vish): Iptables supports chain names of up to 28 characters,  and we
#             add up to 12 characters to binary_name which is used as a prefix,
#             so we limit it to 16 characters.
#             (max_chain_name_length - len('-POSTROUTING') == 16)
def get_binary_name():
    """Grab the name of the binary we're running in."""
    return os.path.basename(inspect.stack()[-1][1])[:16]

binary_name = get_binary_name()


class IptablesRule(object):
    """An iptables rule.

    You shouldn't need to use this class directly, it's only used by
    IptablesManager.

    """

    def __init__(self, chain, rule, wrap=True, top=False):
        self.chain = chain
        self.rule = rule
        self.wrap = wrap
        self.top = top

    def __eq__(self, other):
        return ((self.chain == other.chain) and
                (self.rule == other.rule) and
                (self.top == other.top) and
                (self.wrap == other.wrap))

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        if self.wrap:
            chain = '%s-%s' % (binary_name, self.chain)
        else:
            chain = self.chain
        # new rules should have a zero [packet: byte] count
        return '[0:0] -A %s %s' % (chain, self.rule)


class IptablesTable(object):
    """An iptables table."""

    def __init__(self):
        self.rules = []
        self.remove_rules = []
        self.chains = set()
        self.unwrapped_chains = set()
        self.remove_chains = set()
        self.dirty = True

    def has_chain(self, name, wrap=True):
        if wrap:
            return name in self.chains
        else:
            return name in self.unwrapped_chains

    def add_chain(self, name, wrap=True):
        """Adds a named chain to the table.

        The chain name is wrapped to be unique for the component creating
        it, so different components of Nova can safely create identically
        named chains without interfering with one another.

        At the moment, its wrapped name is <binary name>-<chain name>,
        so if nova-compute creates a chain named 'OUTPUT', it'll actually
        end up named 'nova-compute-OUTPUT'.

        """
        if wrap:
            self.chains.add(name)
        else:
            self.unwrapped_chains.add(name)
        self.dirty = True

    def remove_chain(self, name, wrap=True):
        """Remove named chain.

        This removal "cascades". All rule in the chain are removed, as are
        all rules in other chains that jump to it.

        If the chain is not found, this is merely logged.

        """
        if wrap:
            chain_set = self.chains
        else:
            chain_set = self.unwrapped_chains

        if name not in chain_set:
            LOG.warn(_('Attempted to remove chain %s which does not exist'),
                     name)
            return
        self.dirty = True

        # non-wrapped chains and rules need to be dealt with specially,
        # so we keep a list of them to be iterated over in apply()
        if not wrap:
            self.remove_chains.add(name)
        chain_set.remove(name)
        if not wrap:
            self.remove_rules += filter(lambda r: r.chain == name, self.rules)
        self.rules = filter(lambda r: r.chain != name, self.rules)

        if wrap:
            jump_snippet = '-j %s-%s' % (binary_name, name)
        else:
            jump_snippet = '-j %s' % (name,)

        if not wrap:
            self.remove_rules += filter(lambda r: jump_snippet in r.rule,
                                        self.rules)
        self.rules = filter(lambda r: jump_snippet not in r.rule, self.rules)

    def add_rule(self, chain, rule, wrap=True, top=False):
        """Add a rule to the table.

        This is just like what you'd feed to iptables, just without
        the '-A <chain name>' bit at the start.

        However, if you need to jump to one of your wrapped chains,
        prepend its name with a '$' which will ensure the wrapping
        is applied correctly.

        """
        if wrap and chain not in self.chains:
            raise ValueError(_('Unknown chain: %r') % chain)

        if '$' in rule:
            rule = ' '.join(map(self._wrap_target_chain, rule.split(' ')))

        rule_obj = IptablesRule(chain, rule, wrap, top)
        if rule_obj in self.rules:
            LOG.debug("Skipping duplicate iptables rule addition. "
                      "%(rule)r already in %(rules)r",
                      {'rule': rule_obj, 'rules': self.rules})
        else:
            self.rules.append(IptablesRule(chain, rule, wrap, top))
            self.dirty = True

    def _wrap_target_chain(self, s):
        if s.startswith('$'):
            return '%s-%s' % (binary_name, s[1:])
        return s

    def remove_rule(self, chain, rule, wrap=True, top=False):
        """Remove a rule from a chain.

        Note: The rule must be exactly identical to the one that was added.
        You cannot switch arguments around like you can with the iptables
        CLI tool.

        """
        try:
            self.rules.remove(IptablesRule(chain, rule, wrap, top))
            if not wrap:
                self.remove_rules.append(IptablesRule(chain, rule, wrap, top))
            self.dirty = True
        except ValueError:
            LOG.warn(_('Tried to remove rule that was not there:'
                       ' %(chain)r %(rule)r %(wrap)r %(top)r'),
                     {'chain': chain, 'rule': rule,
                      'top': top, 'wrap': wrap})

    def remove_rules_regex(self, regex):
        """Remove all rules matching regex."""
        if isinstance(regex, six.string_types):
            regex = re.compile(regex)
        num_rules = len(self.rules)
        self.rules = filter(lambda r: not regex.match(str(r)), self.rules)
        removed = num_rules - len(self.rules)
        if removed > 0:
            self.dirty = True
        return removed

    def empty_chain(self, chain, wrap=True):
        """Remove all rules from a chain."""
        chained_rules = [rule for rule in self.rules
                              if rule.chain == chain and rule.wrap == wrap]
        if chained_rules:
            self.dirty = True
        for rule in chained_rules:
            self.rules.remove(rule)


class IptablesManager(object):
    """Wrapper for iptables.

    See IptablesTable for some usage docs

    A number of chains are set up to begin with.

    First, nova-filter-top. It's added at the top of FORWARD and OUTPUT. Its
    name is not wrapped, so it's shared between the various nova workers. It's
    intended for rules that need to live at the top of the FORWARD and OUTPUT
    chains. It's in both the ipv4 and ipv6 set of tables.

    For ipv4 and ipv6, the built-in INPUT, OUTPUT, and FORWARD filter chains
    are wrapped, meaning that the "real" INPUT chain has a rule that jumps to
    the wrapped INPUT chain, etc. Additionally, there's a wrapped chain named
    "local" which is jumped to from nova-filter-top.

    For ipv4, the built-in PREROUTING, OUTPUT, and POSTROUTING nat chains are
    wrapped in the same was as the built-in filter chains. Additionally,
    there's a snat chain that is applied after the POSTROUTING chain.

    """

    def __init__(self, execute=None):
        if not execute:
            self.execute = _execute
        else:
            self.execute = execute

        self.ipv4 = {'filter': IptablesTable(),
                     'nat': IptablesTable(),
                     'mangle': IptablesTable()}
        self.ipv6 = {'filter': IptablesTable()}

        self.iptables_apply_deferred = False

        # Add a nova-filter-top chain. It's intended to be shared
        # among the various nova components. It sits at the very top
        # of FORWARD and OUTPUT.
        for tables in [self.ipv4, self.ipv6]:
            tables['filter'].add_chain('nova-filter-top', wrap=False)
            tables['filter'].add_rule('FORWARD', '-j nova-filter-top',
                                      wrap=False, top=True)
            tables['filter'].add_rule('OUTPUT', '-j nova-filter-top',
                                      wrap=False, top=True)

            tables['filter'].add_chain('local')
            tables['filter'].add_rule('nova-filter-top', '-j $local',
                                      wrap=False)

        # Wrap the built-in chains
        builtin_chains = {4: {'filter': ['INPUT', 'OUTPUT', 'FORWARD'],
                              'nat': ['PREROUTING', 'OUTPUT', 'POSTROUTING'],
                              'mangle': ['POSTROUTING']},
                          6: {'filter': ['INPUT', 'OUTPUT', 'FORWARD']}}

        for ip_version in builtin_chains:
            if ip_version == 4:
                tables = self.ipv4
            elif ip_version == 6:
                tables = self.ipv6

            for table, chains in builtin_chains[ip_version].iteritems():
                for chain in chains:
                    tables[table].add_chain(chain)
                    tables[table].add_rule(chain, '-j $%s' % (chain,),
                                           wrap=False)

        # Add a nova-postrouting-bottom chain. It's intended to be shared
        # among the various nova components. We set it as the last chain
        # of POSTROUTING chain.
        self.ipv4['nat'].add_chain('nova-postrouting-bottom', wrap=False)
        self.ipv4['nat'].add_rule('POSTROUTING', '-j nova-postrouting-bottom',
                                  wrap=False)

        # We add a snat chain to the shared nova-postrouting-bottom chain
        # so that it's applied last.
        self.ipv4['nat'].add_chain('snat')
        self.ipv4['nat'].add_rule('nova-postrouting-bottom', '-j $snat',
                                  wrap=False)

        # And then we add a float-snat chain and jump to first thing in
        # the snat chain.
        self.ipv4['nat'].add_chain('float-snat')
        self.ipv4['nat'].add_rule('snat', '-j $float-snat')

    def defer_apply_on(self):
        self.iptables_apply_deferred = True

    def defer_apply_off(self):
        self.iptables_apply_deferred = False
        self.apply()

    def dirty(self):
        for table in self.ipv4.itervalues():
            if table.dirty:
                return True
        if CONF.use_ipv6:
            for table in self.ipv6.itervalues():
                if table.dirty:
                    return True
        return False

    def apply(self):
        if self.iptables_apply_deferred:
            return
        if self.dirty():
            self._apply()
        else:
            LOG.debug("Skipping apply due to lack of new rules")

    @utils.synchronized('iptables', external=True)
    def _apply(self):
        """Apply the current in-memory set of iptables rules.

        This will blow away any rules left over from previous runs of the
        same component of Nova, and replace them with our current set of
        rules. This happens atomically, thanks to iptables-restore.

        """
        s = [('iptables', self.ipv4)]
        if CONF.use_ipv6:
            s += [('ip6tables', self.ipv6)]

        for cmd, tables in s:
            all_tables, _err = self.execute('%s-save' % (cmd,), '-c',
                                                run_as_root=True,
                                                attempts=5)
            all_lines = all_tables.split('\n')
            for table_name, table in tables.iteritems():
                start, end = self._find_table(all_lines, table_name)
                all_lines[start:end] = self._modify_rules(
                        all_lines[start:end], table, table_name)
                table.dirty = False
            self.execute('%s-restore' % (cmd,), '-c', run_as_root=True,
                         process_input='\n'.join(all_lines),
                         attempts=5)
        LOG.debug("IPTablesManager.apply completed with success")

    def _find_table(self, lines, table_name):
        if len(lines) < 3:
            # length only <2 when fake iptables
            return (0, 0)
        try:
            start = lines.index('*%s' % table_name) - 1
        except ValueError:
            # Couldn't find table_name
            return (0, 0)
        end = lines[start:].index('COMMIT') + start + 2
        return (start, end)

    def _modify_rules(self, current_lines, table, table_name):
        unwrapped_chains = table.unwrapped_chains
        chains = table.chains
        remove_chains = table.remove_chains
        rules = table.rules
        remove_rules = table.remove_rules

        if not current_lines:
            fake_table = ['#Generated by nova',
                          '*' + table_name, 'COMMIT',
                          '#Completed by nova']
            current_lines = fake_table

        # Remove any trace of our rules
        new_filter = filter(lambda line: binary_name not in line,
                            current_lines)

        top_rules = []
        bottom_rules = []

        if CONF.iptables_top_regex:
            regex = re.compile(CONF.iptables_top_regex)
            temp_filter = filter(lambda line: regex.search(line), new_filter)
            for rule_str in temp_filter:
                new_filter = filter(lambda s: s.strip() != rule_str.strip(),
                                    new_filter)
            top_rules = temp_filter

        if CONF.iptables_bottom_regex:
            regex = re.compile(CONF.iptables_bottom_regex)
            temp_filter = filter(lambda line: regex.search(line), new_filter)
            for rule_str in temp_filter:
                new_filter = filter(lambda s: s.strip() != rule_str.strip(),
                    new_filter)
            bottom_rules = temp_filter

        seen_chains = False
        rules_index = 0
        for rules_index, rule in enumerate(new_filter):
            if not seen_chains:
                if rule.startswith(':'):
                    seen_chains = True
            else:
                if not rule.startswith(':'):
                    break

        if not seen_chains:
            rules_index = 2

        our_rules = top_rules
        bot_rules = []
        for rule in rules:
            rule_str = str(rule)
            if rule.top:
                # rule.top == True means we want this rule to be at the top.
                # Further down, we weed out duplicates from the bottom of the
                # list, so here we remove the dupes ahead of time.

                # We don't want to remove an entry if it has non-zero
                # [packet:byte] counts and replace it with [0:0], so let's
                # go look for a duplicate, and over-ride our table rule if
                # found.

                # ignore [packet:byte] counts at beginning of line
                if rule_str.startswith('['):
                    rule_str = rule_str.split(']', 1)[1]
                dup_filter = filter(lambda s: rule_str.strip() in s.strip(),
                                    new_filter)

                new_filter = filter(lambda s:
                                    rule_str.strip() not in s.strip(),
                                    new_filter)
                # if no duplicates, use original rule
                if dup_filter:
                    # grab the last entry, if there is one
                    dup = dup_filter[-1]
                    rule_str = str(dup)
                else:
                    rule_str = str(rule)
                rule_str.strip()

                our_rules += [rule_str]
            else:
                bot_rules += [rule_str]

        our_rules += bot_rules

        new_filter[rules_index:rules_index] = our_rules

        new_filter[rules_index:rules_index] = [':%s - [0:0]' % (name,)
                                               for name in unwrapped_chains]
        new_filter[rules_index:rules_index] = [':%s-%s - [0:0]' %
                                               (binary_name, name,)
                                               for name in chains]

        commit_index = new_filter.index('COMMIT')
        new_filter[commit_index:commit_index] = bottom_rules
        seen_lines = set()

        def _weed_out_duplicates(line):
            # ignore [packet:byte] counts at beginning of lines
            if line.startswith('['):
                line = line.split(']', 1)[1]
            line = line.strip()
            if line in seen_lines:
                return False
            else:
                seen_lines.add(line)
                return True

        def _weed_out_removes(line):
            # We need to find exact matches here
            if line.startswith(':'):
                # it's a chain, for example, ":nova-billing - [0:0]"
                # strip off everything except the chain name
                line = line.split(':')[1]
                line = line.split('- [')[0]
                line = line.strip()
                for chain in remove_chains:
                    if chain == line:
                        remove_chains.remove(chain)
                        return False
            elif line.startswith('['):
                # it's a rule
                # ignore [packet:byte] counts at beginning of lines
                line = line.split(']', 1)[1]
                line = line.strip()
                for rule in remove_rules:
                    # ignore [packet:byte] counts at beginning of rules
                    rule_str = str(rule)
                    rule_str = rule_str.split(' ', 1)[1]
                    rule_str = rule_str.strip()
                    if rule_str == line:
                        remove_rules.remove(rule)
                        return False

            # Leave it alone
            return True

        # We filter duplicates, letting the *last* occurrence take
        # precedence.  We also filter out anything in the "remove"
        # lists.
        new_filter.reverse()
        new_filter = filter(_weed_out_duplicates, new_filter)
        new_filter = filter(_weed_out_removes, new_filter)
        new_filter.reverse()

        # flush lists, just in case we didn't find something
        remove_chains.clear()
        for rule in remove_rules:
            remove_rules.remove(rule)

        return new_filter


# NOTE(jkoelker) This is just a nice little stub point since mocking
#                builtins with mox is a nightmare
def write_to_file(file, data, mode='w'):
    with open(file, mode) as f:
        f.write(data)


def metadata_forward():
    """Create forwarding rule for metadata."""
    if CONF.metadata_host != '127.0.0.1':
        iptables_manager.ipv4['nat'].add_rule('PREROUTING',
                                          '-s 0.0.0.0/0 -d 169.254.169.254/32 '
                                          '-p tcp -m tcp --dport 80 -j DNAT '
                                          '--to-destination %s:%s' %
                                          (CONF.metadata_host,
                                           CONF.metadata_port))
    else:
        iptables_manager.ipv4['nat'].add_rule('PREROUTING',
                                          '-s 0.0.0.0/0 -d 169.254.169.254/32 '
                                          '-p tcp -m tcp --dport 80 '
                                          '-j REDIRECT --to-ports %s' %
                                           CONF.metadata_port)
    iptables_manager.apply()


def metadata_accept():
    """Create the filter accept rule for metadata."""
    rule = '-s 0.0.0.0/0 -p tcp -m tcp --dport %s' % CONF.metadata_port
    if CONF.metadata_host != '127.0.0.1':
        rule += ' -d %s -j ACCEPT' % CONF.metadata_host
    else:
        rule += ' -m addrtype --dst-type LOCAL -j ACCEPT'
    iptables_manager.ipv4['filter'].add_rule('INPUT', rule)
    iptables_manager.apply()


def add_snat_rule(ip_range, is_external=False):
    if CONF.routing_source_ip:
        if is_external:
            if CONF.force_snat_range:
                snat_range = CONF.force_snat_range
            else:
                snat_range = []
        else:
            snat_range = ['0.0.0.0/0']
        for dest_range in snat_range:
            rule = ('-s %s -d %s -j SNAT --to-source %s'
                    % (ip_range, dest_range, CONF.routing_source_ip))
            if not is_external and CONF.public_interface:
                rule += ' -o %s' % CONF.public_interface
            iptables_manager.ipv4['nat'].add_rule('snat', rule)
        iptables_manager.apply()


def init_host(ip_range, is_external=False):
    """Basic networking setup goes here."""
    # NOTE(devcamcar): Cloud public SNAT entries and the default
    # SNAT rule for outbound traffic.

    add_snat_rule(ip_range, is_external)

    rules = []
    if is_external:
        for snat_range in CONF.force_snat_range:
            rules.append('PREROUTING -p ipv4 --ip-src %s --ip-dst %s '
                         '-j redirect --redirect-target ACCEPT' %
                         (ip_range, snat_range))
    if rules:
        ensure_ebtables_rules(rules, 'nat')

    iptables_manager.ipv4['nat'].add_rule('POSTROUTING',
                                          '-s %s -d %s/32 -j ACCEPT' %
                                          (ip_range, CONF.metadata_host))

    for dmz in CONF.dmz_cidr:
        iptables_manager.ipv4['nat'].add_rule('POSTROUTING',
                                              '-s %s -d %s -j ACCEPT' %
                                              (ip_range, dmz))

    iptables_manager.ipv4['nat'].add_rule('POSTROUTING',
                                          '-s %(range)s -d %(range)s '
                                          '-m conntrack ! --ctstate DNAT '
                                          '-j ACCEPT' %
                                          {'range': ip_range})
    iptables_manager.apply()


def send_arp_for_ip(ip, device, count):
    out, err = _execute('arping', '-U', ip,
                        '-A', '-I', device,
                        '-c', str(count),
                        run_as_root=True, check_exit_code=False)

    if err:
        LOG.debug('arping error for ip %s', ip)


def bind_floating_ip(floating_ip, device):
    """Bind ip to public interface."""
    _execute('ip', 'addr', 'add', str(floating_ip) + '/32',
             'dev', device,
             run_as_root=True, check_exit_code=[0, 2, 254])

    if CONF.send_arp_for_ha and CONF.send_arp_for_ha_count > 0:
        send_arp_for_ip(floating_ip, device, CONF.send_arp_for_ha_count)


def unbind_floating_ip(floating_ip, device):
    """Unbind a public ip from public interface."""
    _execute('ip', 'addr', 'del', str(floating_ip) + '/32',
             'dev', device,
             run_as_root=True, check_exit_code=[0, 2, 254])


def ensure_metadata_ip():
    """Sets up local metadata ip."""
    _execute('ip', 'addr', 'add', '169.254.169.254/32',
             'scope', 'link', 'dev', 'lo',
             run_as_root=True, check_exit_code=[0, 2, 254])


def ensure_vpn_forward(public_ip, port, private_ip):
    """Sets up forwarding rules for vlan."""
    iptables_manager.ipv4['filter'].add_rule('FORWARD',
                                             '-d %s -p udp '
                                             '--dport 1194 '
                                             '-j ACCEPT' % private_ip)
    iptables_manager.ipv4['nat'].add_rule('PREROUTING',
                                          '-d %s -p udp '
                                          '--dport %s -j DNAT --to %s:1194' %
                                          (public_ip, port, private_ip))
    iptables_manager.ipv4['nat'].add_rule('OUTPUT',
                                          '-d %s -p udp '
                                          '--dport %s -j DNAT --to %s:1194' %
                                          (public_ip, port, private_ip))
    iptables_manager.apply()


def ensure_floating_forward(floating_ip, fixed_ip, device, network):
    """Ensure floating ip forwarding rule."""
    # NOTE(vish): Make sure we never have duplicate rules for the same ip
    regex = '.*\s+%s(/32|\s+|$)' % floating_ip
    num_rules = iptables_manager.ipv4['nat'].remove_rules_regex(regex)
    if num_rules:
        msg = _('Removed %(num)d duplicate rules for floating ip %(float)s')
        LOG.warn(msg % {'num': num_rules, 'float': floating_ip})
    for chain, rule in floating_forward_rules(floating_ip, fixed_ip, device):
        iptables_manager.ipv4['nat'].add_rule(chain, rule)
    iptables_manager.apply()
    if device != network['bridge']:
        ensure_ebtables_rules(*floating_ebtables_rules(fixed_ip, network))


def remove_floating_forward(floating_ip, fixed_ip, device, network):
    """Remove forwarding for floating ip."""
    for chain, rule in floating_forward_rules(floating_ip, fixed_ip, device):
        iptables_manager.ipv4['nat'].remove_rule(chain, rule)
    iptables_manager.apply()
    if device != network['bridge']:
        remove_ebtables_rules(*floating_ebtables_rules(fixed_ip, network))


def floating_ebtables_rules(fixed_ip, network):
    """Makes sure only in-network traffic is bridged."""
    return (['PREROUTING --logical-in %s -p ipv4 --ip-src %s '
            '! --ip-dst %s -j redirect --redirect-target ACCEPT' %
            (network['bridge'], fixed_ip, network['cidr'])], 'nat')


def floating_forward_rules(floating_ip, fixed_ip, device):
    rules = []
    rule = '-s %s -j SNAT --to %s' % (fixed_ip, floating_ip)
    if device:
        rules.append(('float-snat', rule + ' -d %s' % fixed_ip))
        rules.append(('float-snat', rule + ' -o %s' % device))
    else:
        rules.append(('float-snat', rule))
    rules.append(
            ('PREROUTING', '-d %s -j DNAT --to %s' % (floating_ip, fixed_ip)))
    rules.append(
            ('OUTPUT', '-d %s -j DNAT --to %s' % (floating_ip, fixed_ip)))
    rules.append(('POSTROUTING', '-s %s -m conntrack --ctstate DNAT -j SNAT '
                  '--to-source %s' %
                  (fixed_ip, floating_ip)))
    return rules


def clean_conntrack(fixed_ip):
    try:
        _execute('conntrack', '-D', '-r', fixed_ip, run_as_root=True,
                 check_exit_code=[0, 1])
    except processutils.ProcessExecutionError:
        LOG.exception(_('Error deleting conntrack entries for %s'), fixed_ip)


def _enable_ipv4_forwarding():
    sysctl_key = 'net.ipv4.ip_forward'
    stdout, stderr = _execute('sysctl', '-n', sysctl_key)
    if stdout.strip() is not '1':
        _execute('sysctl', '-w', '%s=1' % sysctl_key, run_as_root=True)


@utils.synchronized('lock_gateway', external=True)
def initialize_gateway_device(dev, network_ref):
    if not network_ref:
        return

    _enable_ipv4_forwarding()

    # NOTE(vish): The ip for dnsmasq has to be the first address on the
    #             bridge for it to respond to requests properly
    try:
        prefix = network_ref.cidr.prefixlen
    except AttributeError:
        prefix = network_ref['cidr'].rpartition('/')[2]

    full_ip = '%s/%s' % (network_ref['dhcp_server'], prefix)
    new_ip_params = [[full_ip, 'brd', network_ref['broadcast']]]
    old_ip_params = []
    out, err = _execute('ip', 'addr', 'show', 'dev', dev,
                        'scope', 'global')
    for line in out.split('\n'):
        fields = line.split()
        if fields and fields[0] == 'inet':
            ip_params = fields[1:-1]
            old_ip_params.append(ip_params)
            if ip_params[0] != full_ip:
                new_ip_params.append(ip_params)
    if not old_ip_params or old_ip_params[0][0] != full_ip:
        old_routes = []
        result = _execute('ip', 'route', 'show', 'dev', dev)
        if result:
            out, err = result
            for line in out.split('\n'):
                fields = line.split()
                if fields and 'via' in fields:
                    old_routes.append(fields)
                    _execute('ip', 'route', 'del', fields[0],
                             'dev', dev, run_as_root=True)
        for ip_params in old_ip_params:
            _execute(*_ip_bridge_cmd('del', ip_params, dev),
                     run_as_root=True, check_exit_code=[0, 2, 254])
        for ip_params in new_ip_params:
            _execute(*_ip_bridge_cmd('add', ip_params, dev),
                     run_as_root=True, check_exit_code=[0, 2, 254])

        for fields in old_routes:
            _execute('ip', 'route', 'add', *fields,
                     run_as_root=True)
        if CONF.send_arp_for_ha and CONF.send_arp_for_ha_count > 0:
            send_arp_for_ip(network_ref['dhcp_server'], dev,
                            CONF.send_arp_for_ha_count)
    if CONF.use_ipv6:
        _execute('ip', '-f', 'inet6', 'addr',
                 'change', network_ref['cidr_v6'],
                 'dev', dev, run_as_root=True)


def get_dhcp_leases(context, network_ref):
    """Return a network's hosts config in dnsmasq leasefile format."""
    hosts = []
    host = None
    if network_ref['multi_host']:
        host = CONF.host
    for fixedip in objects.FixedIPList.get_by_network(context,
                                                      network_ref,
                                                      host=host):
        # NOTE(cfb): Don't return a lease entry if the IP isn't
        #            already leased
        if fixedip.leased:
            hosts.append(_host_lease(fixedip))

    return '\n'.join(hosts)


def get_dhcp_hosts(context, network_ref, fixedips):
    """Get network's hosts config in dhcp-host format."""
    hosts = []
    macs = set()
    for fixedip in fixedips:
        if fixedip.allocated:
            if fixedip.virtual_interface.address not in macs:
                hosts.append(_host_dhcp(fixedip))
                macs.add(fixedip.virtual_interface.address)
    return '\n'.join(hosts)


def get_dns_hosts(context, network_ref):
    """Get network's DNS hosts in hosts format."""
    hosts = []
    for fixedip in objects.FixedIPList.get_by_network(context, network_ref):
        if fixedip.allocated:
            hosts.append(_host_dns(fixedip))
    return '\n'.join(hosts)


def _add_dnsmasq_accept_rules(dev):
    """Allow DHCP and DNS traffic through to dnsmasq."""
    table = iptables_manager.ipv4['filter']
    for port in [67, 53]:
        for proto in ['udp', 'tcp']:
            args = {'dev': dev, 'port': port, 'proto': proto}
            table.add_rule('INPUT',
                           '-i %(dev)s -p %(proto)s -m %(proto)s '
                           '--dport %(port)s -j ACCEPT' % args)
    iptables_manager.apply()


def _remove_dnsmasq_accept_rules(dev):
    """Remove DHCP and DNS traffic allowed through to dnsmasq."""
    table = iptables_manager.ipv4['filter']
    for port in [67, 53]:
        for proto in ['udp', 'tcp']:
            args = {'dev': dev, 'port': port, 'proto': proto}
            table.remove_rule('INPUT',
                           '-i %(dev)s -p %(proto)s -m %(proto)s '
                           '--dport %(port)s -j ACCEPT' % args)
    iptables_manager.apply()


# NOTE(russellb) Curious why this is needed?  Check out this explanation from
# markmc: https://bugzilla.redhat.com/show_bug.cgi?id=910619#c6
def _add_dhcp_mangle_rule(dev):
    table = iptables_manager.ipv4['mangle']
    table.add_rule('POSTROUTING',
                   '-o %s -p udp -m udp --dport 68 -j CHECKSUM '
                   '--checksum-fill' % dev)
    iptables_manager.apply()


def _remove_dhcp_mangle_rule(dev):
    table = iptables_manager.ipv4['mangle']
    table.remove_rule('POSTROUTING',
                      '-o %s -p udp -m udp --dport 68 -j CHECKSUM '
                      '--checksum-fill' % dev)
    iptables_manager.apply()


def get_dhcp_opts(context, network_ref, fixedips):
    """Get network's hosts config in dhcp-opts format."""
    gateway = network_ref['gateway']
    # NOTE(vish): if we are in multi-host mode and we are not sharing
    #             addresses, then we actually need to hand out the
    #             dhcp server address as the gateway.
    if network_ref['multi_host'] and not (network_ref['share_address'] or
                                          CONF.share_dhcp_address):
        gateway = network_ref['dhcp_server']
    hosts = []
    if CONF.use_single_default_gateway:
        for fixedip in fixedips:
            if fixedip.allocated:
                vif_id = fixedip.virtual_interface_id
                if fixedip.default_route:
                    hosts.append(_host_dhcp_opts(vif_id, gateway))
                else:
                    hosts.append(_host_dhcp_opts(vif_id))
    else:
        hosts.append(_host_dhcp_opts(None, gateway))
    return '\n'.join(hosts)


def release_dhcp(dev, address, mac_address):
    try:
        utils.execute('dhcp_release', dev, address, mac_address,
                      run_as_root=True)
    except processutils.ProcessExecutionError:
        raise exception.NetworkDhcpReleaseFailed(address=address,
                                                 mac_address=mac_address)


def update_dhcp(context, dev, network_ref):
    conffile = _dhcp_file(dev, 'conf')
    host = None
    if network_ref['multi_host']:
        host = CONF.host
    fixedips = objects.FixedIPList.get_by_network(context,
                                                  network_ref,
                                                  host=host)
    write_to_file(conffile, get_dhcp_hosts(context, network_ref, fixedips))
    restart_dhcp(context, dev, network_ref, fixedips)


def update_dns(context, dev, network_ref):
    hostsfile = _dhcp_file(dev, 'hosts')
    host = None
    if network_ref['multi_host']:
        host = CONF.host
    fixedips = objects.FixedIPList.get_by_network(context,
                                                  network_ref,
                                                  host=host)
    write_to_file(hostsfile, get_dns_hosts(context, network_ref))
    restart_dhcp(context, dev, network_ref, fixedips)


def update_dhcp_hostfile_with_text(dev, hosts_text):
    conffile = _dhcp_file(dev, 'conf')
    write_to_file(conffile, hosts_text)


def kill_dhcp(dev):
    pid = _dnsmasq_pid_for(dev)
    if pid:
        # Check that the process exists and looks like a dnsmasq process
        conffile = _dhcp_file(dev, 'conf')
        out, _err = _execute('cat', '/proc/%d/cmdline' % pid,
                             check_exit_code=False)
        if conffile.split('/')[-1] in out:
            _execute('kill', '-9', pid, run_as_root=True)
        else:
            LOG.debug('Pid %d is stale, skip killing dnsmasq', pid)
    _remove_dnsmasq_accept_rules(dev)
    _remove_dhcp_mangle_rule(dev)


# NOTE(ja): Sending a HUP only reloads the hostfile, so any
#           configuration options (like dchp-range, vlan, ...)
#           aren't reloaded.
@utils.synchronized('dnsmasq_start')
def restart_dhcp(context, dev, network_ref, fixedips):
    """(Re)starts a dnsmasq server for a given network.

    If a dnsmasq instance is already running then send a HUP
    signal causing it to reload, otherwise spawn a new instance.

    """
    conffile = _dhcp_file(dev, 'conf')

    optsfile = _dhcp_file(dev, 'opts')
    write_to_file(optsfile, get_dhcp_opts(context, network_ref, fixedips))
    os.chmod(optsfile, 0o644)

    _add_dhcp_mangle_rule(dev)

    # Make sure dnsmasq can actually read it (it setuid()s to "nobody")
    os.chmod(conffile, 0o644)

    pid = _dnsmasq_pid_for(dev)

    # if dnsmasq is already running, then tell it to reload
    if pid:
        out, _err = _execute('cat', '/proc/%d/cmdline' % pid,
                             check_exit_code=False)
        # Using symlinks can cause problems here so just compare the name
        # of the file itself
        if conffile.split('/')[-1] in out:
            try:
                _execute('kill', '-HUP', pid, run_as_root=True)
                _add_dnsmasq_accept_rules(dev)
                return
            except Exception as exc:  # pylint: disable=W0703
                LOG.error(_('Hupping dnsmasq threw %s'), exc)
        else:
            LOG.debug('Pid %d is stale, relaunching dnsmasq', pid)

    cmd = ['env',
           'CONFIG_FILE=%s' % jsonutils.dumps(CONF.dhcpbridge_flagfile),
           'NETWORK_ID=%s' % str(network_ref['id']),
           'dnsmasq',
           '--strict-order',
           '--bind-interfaces',
           '--conf-file=%s' % CONF.dnsmasq_config_file,
           '--pid-file=%s' % _dhcp_file(dev, 'pid'),
           '--dhcp-optsfile=%s' % _dhcp_file(dev, 'opts'),
           '--listen-address=%s' % network_ref['dhcp_server'],
           '--except-interface=lo',
           '--dhcp-range=set:%s,%s,static,%s,%ss' %
                         (network_ref['label'],
                          network_ref['dhcp_start'],
                          network_ref['netmask'],
                          CONF.dhcp_lease_time),
           '--dhcp-lease-max=%s' % len(netaddr.IPNetwork(network_ref['cidr'])),
           '--dhcp-hostsfile=%s' % _dhcp_file(dev, 'conf'),
           '--dhcp-script=%s' % CONF.dhcpbridge,
           '--no-hosts',
           '--leasefile-ro']

    # dnsmasq currently gives an error for an empty domain,
    # rather than ignoring.  So only specify it if defined.
    if CONF.dhcp_domain:
        cmd.append('--domain=%s' % CONF.dhcp_domain)

    dns_servers = set(CONF.dns_server)
    if CONF.use_network_dns_servers:
        if network_ref.get('dns1'):
            dns_servers.add(network_ref.get('dns1'))
        if network_ref.get('dns2'):
            dns_servers.add(network_ref.get('dns2'))
    if network_ref['multi_host']:
        cmd.append('--addn-hosts=%s' % _dhcp_file(dev, 'hosts'))
    if dns_servers:
        cmd.append('--no-resolv')
    for dns_server in dns_servers:
        cmd.append('--server=%s' % dns_server)

    _execute(*cmd, run_as_root=True)

    _add_dnsmasq_accept_rules(dev)


@utils.synchronized('radvd_start')
def update_ra(context, dev, network_ref):
    conffile = _ra_file(dev, 'conf')
    conf_str = """
interface %s
{
   AdvSendAdvert on;
   MinRtrAdvInterval 3;
   MaxRtrAdvInterval 10;
   prefix %s
   {
        AdvOnLink on;
        AdvAutonomous on;
   };
};
""" % (dev, network_ref['cidr_v6'])
    write_to_file(conffile, conf_str)

    # Make sure radvd can actually read it (it setuid()s to "nobody")
    os.chmod(conffile, 0o644)

    pid = _ra_pid_for(dev)

    # if radvd is already running, then tell it to reload
    if pid:
        out, _err = _execute('cat', '/proc/%d/cmdline'
                             % pid, check_exit_code=False)
        if conffile in out:
            try:
                _execute('kill', pid, run_as_root=True)
            except Exception as exc:  # pylint: disable=W0703
                LOG.error(_('killing radvd threw %s'), exc)
        else:
            LOG.debug('Pid %d is stale, relaunching radvd', pid)

    cmd = ['radvd',
           '-C', '%s' % _ra_file(dev, 'conf'),
           '-p', '%s' % _ra_file(dev, 'pid')]

    _execute(*cmd, run_as_root=True)


def _host_lease(fixedip):
    """Return a host string for an address in leasefile format."""
    timestamp = timeutils.utcnow()
    seconds_since_epoch = calendar.timegm(timestamp.utctimetuple())
    return '%d %s %s %s *' % (seconds_since_epoch + CONF.dhcp_lease_time,
                              fixedip.virtual_interface.address,
                              fixedip.address,
                              fixedip.instance.hostname or '*')


def _host_dhcp_network(vif_id):
    return 'NW-%s' % vif_id


def _host_dhcp(fixedip):
    """Return a host string for an address in dhcp-host format."""
    if CONF.use_single_default_gateway:
        net = _host_dhcp_network(fixedip.virtual_interface_id)
        return '%s,%s.%s,%s,net:%s' % (fixedip.virtual_interface.address,
                               fixedip.instance.hostname,
                               CONF.dhcp_domain,
                               fixedip.address,
                               net)
    else:
        return '%s,%s.%s,%s' % (fixedip.virtual_interface.address,
                               fixedip.instance.hostname,
                               CONF.dhcp_domain,
                               fixedip.address)


def _host_dns(fixedip):
    return '%s\t%s.%s' % (fixedip.address,
                          fixedip.instance.hostname,
                          CONF.dhcp_domain)


def _host_dhcp_opts(vif_id=None, gateway=None):
    """Return an empty gateway option."""
    values = []
    if vif_id is not None:
        values.append(_host_dhcp_network(vif_id))
    # NOTE(vish): 3 is the dhcp option for gateway.
    values.append('3')
    if gateway:
        values.append('%s' % gateway)
    return ','.join(values)


def _execute(*cmd, **kwargs):
    """Wrapper around utils._execute for fake_network."""
    if CONF.fake_network:
        LOG.debug('FAKE NET: %s', ' '.join(map(str, cmd)))
        return 'fake', 0
    else:
        return utils.execute(*cmd, **kwargs)


def device_exists(device):
    """Check if ethernet device exists."""
    return os.path.exists('/sys/class/net/%s' % device)


def _dhcp_file(dev, kind):
    """Return path to a pid, leases, hosts or conf file for a bridge/device."""
    fileutils.ensure_tree(CONF.networks_path)
    return os.path.abspath('%s/nova-%s.%s' % (CONF.networks_path,
                                              dev,
                                              kind))


def _ra_file(dev, kind):
    """Return path to a pid or conf file for a bridge/device."""
    fileutils.ensure_tree(CONF.networks_path)
    return os.path.abspath('%s/nova-ra-%s.%s' % (CONF.networks_path,
                                              dev,
                                              kind))


def _dnsmasq_pid_for(dev):
    """Returns the pid for prior dnsmasq instance for a bridge/device.

    Returns None if no pid file exists.

    If machine has rebooted pid might be incorrect (caller should check).

    """
    pid_file = _dhcp_file(dev, 'pid')

    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                return int(f.read())
        except (ValueError, IOError):
            return None


def _ra_pid_for(dev):
    """Returns the pid for prior radvd instance for a bridge/device.

    Returns None if no pid file exists.

    If machine has rebooted pid might be incorrect (caller should check).

    """
    pid_file = _ra_file(dev, 'pid')

    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            return int(f.read())


def _ip_bridge_cmd(action, params, device):
    """Build commands to add/del ips to bridges/devices."""
    cmd = ['ip', 'addr', action]
    cmd.extend(params)
    cmd.extend(['dev', device])
    return cmd


def _set_device_mtu(dev, mtu=None):
    """Set the device MTU."""

    if not mtu:
        mtu = CONF.network_device_mtu
    if mtu:
        utils.execute('ip', 'link', 'set', dev, 'mtu',
                      mtu, run_as_root=True,
                      check_exit_code=[0, 2, 254])


def _create_veth_pair(dev1_name, dev2_name):
    """Create a pair of veth devices with the specified names,
    deleting any previous devices with those names.
    """
    for dev in [dev1_name, dev2_name]:
        delete_net_dev(dev)

    utils.execute('ip', 'link', 'add', dev1_name, 'type', 'veth', 'peer',
                  'name', dev2_name, run_as_root=True)
    for dev in [dev1_name, dev2_name]:
        utils.execute('ip', 'link', 'set', dev, 'up', run_as_root=True)
        utils.execute('ip', 'link', 'set', dev, 'promisc', 'on',
                      run_as_root=True)
        _set_device_mtu(dev)


def _ovs_vsctl(args):
    full_args = ['ovs-vsctl', '--timeout=%s' % CONF.ovs_vsctl_timeout] + args
    try:
        return utils.execute(*full_args, run_as_root=True)
    except Exception as e:
        LOG.error(_("Unable to execute %(cmd)s. Exception: %(exception)s"),
                  {'cmd': full_args, 'exception': e})
        raise exception.AgentError(method=full_args)


def create_ovs_vif_port(bridge, dev, iface_id, mac, instance_id):
    _ovs_vsctl(['--', '--if-exists', 'del-port', dev, '--',
                'add-port', bridge, dev,
                '--', 'set', 'Interface', dev,
                'external-ids:iface-id=%s' % iface_id,
                'external-ids:iface-status=active',
                'external-ids:attached-mac=%s' % mac,
                'external-ids:vm-uuid=%s' % instance_id])
    _set_device_mtu(dev)


def delete_ovs_vif_port(bridge, dev):
    _ovs_vsctl(['--', '--if-exists', 'del-port', bridge, dev])
    delete_net_dev(dev)


def create_ivs_vif_port(dev, iface_id, mac, instance_id):
    utils.execute('ivs-ctl', 'add-port',
                   dev, run_as_root=True)


def delete_ivs_vif_port(dev):
    utils.execute('ivs-ctl', 'del-port', dev,
                  run_as_root=True)
    utils.execute('ip', 'link', 'delete', dev,
                  run_as_root=True)


def create_tap_dev(dev, mac_address=None):
    if not device_exists(dev):
        try:
            # First, try with 'ip'
            utils.execute('ip', 'tuntap', 'add', dev, 'mode', 'tap',
                          run_as_root=True, check_exit_code=[0, 2, 254])
        except processutils.ProcessExecutionError:
            # Second option: tunctl
            utils.execute('tunctl', '-b', '-t', dev, run_as_root=True)
        if mac_address:
            utils.execute('ip', 'link', 'set', dev, 'address', mac_address,
                          run_as_root=True, check_exit_code=[0, 2, 254])
        utils.execute('ip', 'link', 'set', dev, 'up', run_as_root=True,
                      check_exit_code=[0, 2, 254])


def delete_net_dev(dev):
    """Delete a network device only if it exists."""
    if device_exists(dev):
        try:
            utils.execute('ip', 'link', 'delete', dev, run_as_root=True,
                          check_exit_code=[0, 2, 254])
            LOG.debug("Net device removed: '%s'", dev)
        except processutils.ProcessExecutionError:
            with excutils.save_and_reraise_exception():
                LOG.error(_("Failed removing net device: '%s'"), dev)


# Similar to compute virt layers, the Linux network node
# code uses a flexible driver model to support different ways
# of creating ethernet interfaces and attaching them to the network.
# In the case of a network host, these interfaces
# act as gateway/dhcp/vpn/etc. endpoints not VM interfaces.
interface_driver = None


def _get_interface_driver():
    global interface_driver
    if not interface_driver:
        interface_driver = importutils.import_object(
                CONF.linuxnet_interface_driver)
    return interface_driver


def plug(network, mac_address, gateway=True):
    return _get_interface_driver().plug(network, mac_address, gateway)


def unplug(network):
    return _get_interface_driver().unplug(network)


def get_dev(network):
    return _get_interface_driver().get_dev(network)


class LinuxNetInterfaceDriver(object):
    """Abstract class that defines generic network host API
    for all Linux interface drivers.
    """

    def plug(self, network, mac_address):
        """Create Linux device, return device name."""
        raise NotImplementedError()

    def unplug(self, network):
        """Destroy Linux device, return device name."""
        raise NotImplementedError()

    def get_dev(self, network):
        """Get device name."""
        raise NotImplementedError()


# plugs interfaces using Linux Bridge
class LinuxBridgeInterfaceDriver(LinuxNetInterfaceDriver):

    def plug(self, network, mac_address, gateway=True):
        vlan = network.get('vlan')
        if vlan is not None:
            iface = CONF.vlan_interface or network['bridge_interface']
            LinuxBridgeInterfaceDriver.ensure_vlan_bridge(
                           vlan,
                           network['bridge'],
                           iface,
                           network,
                           mac_address,
                           network.get('mtu'))
            iface = 'vlan%s' % vlan
        else:
            iface = CONF.flat_interface or network['bridge_interface']
            LinuxBridgeInterfaceDriver.ensure_bridge(
                          network['bridge'],
                          iface,
                          network, gateway)

        if network['share_address'] or CONF.share_dhcp_address:
            isolate_dhcp_address(iface, network['dhcp_server'])
        # NOTE(vish): applying here so we don't get a lock conflict
        iptables_manager.apply()
        return network['bridge']

    def unplug(self, network, gateway=True):
        vlan = network.get('vlan')
        if vlan is not None:
            iface = 'vlan%s' % vlan
            LinuxBridgeInterfaceDriver.remove_vlan_bridge(vlan,
                                                          network['bridge'])
        else:
            iface = CONF.flat_interface or network['bridge_interface']
            LinuxBridgeInterfaceDriver.remove_bridge(network['bridge'],
                                                     gateway)

        if network['share_address'] or CONF.share_dhcp_address:
            remove_isolate_dhcp_address(iface, network['dhcp_server'])

        iptables_manager.apply()
        return self.get_dev(network)

    def get_dev(self, network):
        return network['bridge']

    @staticmethod
    def ensure_vlan_bridge(vlan_num, bridge, bridge_interface,
                           net_attrs=None, mac_address=None,
                           mtu=None):
        """Create a vlan and bridge unless they already exist."""
        interface = LinuxBridgeInterfaceDriver.ensure_vlan(vlan_num,
                                               bridge_interface, mac_address,
                                               mtu)
        LinuxBridgeInterfaceDriver.ensure_bridge(bridge, interface, net_attrs)
        return interface

    @staticmethod
    def remove_vlan_bridge(vlan_num, bridge):
        """Delete a bridge and vlan."""
        LinuxBridgeInterfaceDriver.remove_bridge(bridge)
        LinuxBridgeInterfaceDriver.remove_vlan(vlan_num)

    @staticmethod
    @utils.synchronized('lock_vlan', external=True)
    def ensure_vlan(vlan_num, bridge_interface, mac_address=None, mtu=None):
        """Create a vlan unless it already exists."""
        interface = 'vlan%s' % vlan_num
        if not device_exists(interface):
            LOG.debug('Starting VLAN interface %s', interface)
            _execute('ip', 'link', 'add', 'link', bridge_interface,
                     'name', interface, 'type', 'vlan',
                     'id', vlan_num, run_as_root=True,
                     check_exit_code=[0, 2, 254])
            # (danwent) the bridge will inherit this address, so we want to
            # make sure it is the value set from the NetworkManager
            if mac_address:
                _execute('ip', 'link', 'set', interface, 'address',
                         mac_address, run_as_root=True,
                         check_exit_code=[0, 2, 254])
            _execute('ip', 'link', 'set', interface, 'up', run_as_root=True,
                     check_exit_code=[0, 2, 254])
        # NOTE(vish): set mtu every time to ensure that changes to mtu get
        #             propogated
        _set_device_mtu(interface, mtu)
        return interface

    @staticmethod
    @utils.synchronized('lock_vlan', external=True)
    def remove_vlan(vlan_num):
        """Delete a vlan."""
        vlan_interface = 'vlan%s' % vlan_num
        delete_net_dev(vlan_interface)

    @staticmethod
    @utils.synchronized('lock_bridge', external=True)
    def ensure_bridge(bridge, interface, net_attrs=None, gateway=True,
                      filtering=True):
        """Create a bridge unless it already exists.

        :param interface: the interface to create the bridge on.
        :param net_attrs: dictionary with  attributes used to create bridge.
        :param gateway: whether or not the bridge is a gateway.
        :param filtering: whether or not to create filters on the bridge.

        If net_attrs is set, it will add the net_attrs['gateway'] to the bridge
        using net_attrs['broadcast'] and net_attrs['cidr'].  It will also add
        the ip_v6 address specified in net_attrs['cidr_v6'] if use_ipv6 is set.

        The code will attempt to move any ips that already exist on the
        interface onto the bridge and reset the default gateway if necessary.

        """
        if not device_exists(bridge):
            LOG.debug('Starting Bridge %s', bridge)
            _execute('brctl', 'addbr', bridge, run_as_root=True)
            _execute('brctl', 'setfd', bridge, 0, run_as_root=True)
            # _execute('brctl setageing %s 10' % bridge, run_as_root=True)
            _execute('brctl', 'stp', bridge, 'off', run_as_root=True)
            # (danwent) bridge device MAC address can't be set directly.
            # instead it inherits the MAC address of the first device on the
            # bridge, which will either be the vlan interface, or a
            # physical NIC.
            _execute('ip', 'link', 'set', bridge, 'up', run_as_root=True)

        if interface:
            msg = _('Adding interface %(interface)s to bridge %(bridge)s')
            LOG.debug(msg, {'interface': interface, 'bridge': bridge})
            out, err = _execute('brctl', 'addif', bridge, interface,
                                check_exit_code=False, run_as_root=True)
            if (err and err != "device %s is already a member of a bridge; "
                     "can't enslave it to bridge %s.\n" % (interface, bridge)):
                msg = _('Failed to add interface: %s') % err
                raise exception.NovaException(msg)

            out, err = _execute('ip', 'link', 'set', interface, 'up',
                                check_exit_code=False, run_as_root=True)

            # NOTE(vish): This will break if there is already an ip on the
            #             interface, so we move any ips to the bridge
            # NOTE(danms): We also need to copy routes to the bridge so as
            #              not to break existing connectivity on the interface
            old_routes = []
            out, err = _execute('ip', 'route', 'show', 'dev', interface)
            for line in out.split('\n'):
                fields = line.split()
                if fields and 'via' in fields:
                    old_routes.append(fields)
                    _execute('ip', 'route', 'del', *fields,
                             run_as_root=True)
            out, err = _execute('ip', 'addr', 'show', 'dev', interface,
                                'scope', 'global')
            for line in out.split('\n'):
                fields = line.split()
                if fields and fields[0] == 'inet':
                    if fields[-2] in ('secondary', 'dynamic', ):
                        params = fields[1:-2]
                    else:
                        params = fields[1:-1]
                    _execute(*_ip_bridge_cmd('del', params, fields[-1]),
                             run_as_root=True, check_exit_code=[0, 2, 254])
                    _execute(*_ip_bridge_cmd('add', params, bridge),
                             run_as_root=True, check_exit_code=[0, 2, 254])
            for fields in old_routes:
                _execute('ip', 'route', 'add', *fields,
                         run_as_root=True)

        if filtering:
            # Don't forward traffic unless we were told to be a gateway
            ipv4_filter = iptables_manager.ipv4['filter']
            if gateway:
                for rule in get_gateway_rules(bridge):
                    ipv4_filter.add_rule(*rule)
            else:
                ipv4_filter.add_rule('FORWARD',
                                     ('--in-interface %s -j %s'
                                      % (bridge, CONF.iptables_drop_action)))
                ipv4_filter.add_rule('FORWARD',
                                     ('--out-interface %s -j %s'
                                      % (bridge, CONF.iptables_drop_action)))

    @staticmethod
    @utils.synchronized('lock_bridge', external=True)
    def remove_bridge(bridge, gateway=True, filtering=True):
        """Delete a bridge."""
        if not device_exists(bridge):
            return
        else:
            if filtering:
                ipv4_filter = iptables_manager.ipv4['filter']
                if gateway:
                    for rule in get_gateway_rules(bridge):
                        ipv4_filter.remove_rule(*rule)
                else:
                    drop_actions = ['DROP']
                    if CONF.iptables_drop_action != 'DROP':
                        drop_actions.append(CONF.iptables_drop_action)

                    for drop_action in drop_actions:
                        ipv4_filter.remove_rule('FORWARD',
                                                ('--in-interface %s -j %s'
                                                 % (bridge, drop_action)))
                        ipv4_filter.remove_rule('FORWARD',
                                                ('--out-interface %s -j %s'
                                                 % (bridge, drop_action)))
            delete_net_dev(bridge)


@utils.synchronized('ebtables', external=True)
def ensure_ebtables_rules(rules, table='filter'):
    for rule in rules:
        cmd = ['ebtables', '-t', table, '-D'] + rule.split()
        _execute(*cmd, check_exit_code=False, run_as_root=True)
        cmd[3] = '-I'
        _execute(*cmd, run_as_root=True)


@utils.synchronized('ebtables', external=True)
def remove_ebtables_rules(rules, table='filter'):
    for rule in rules:
        cmd = ['ebtables', '-t', table, '-D'] + rule.split()
        _execute(*cmd, check_exit_code=False, run_as_root=True)


def isolate_dhcp_address(interface, address):
    # block arp traffic to address across the interface
    rules = []
    rules.append('INPUT -p ARP -i %s --arp-ip-dst %s -j DROP'
                 % (interface, address))
    rules.append('OUTPUT -p ARP -o %s --arp-ip-src %s -j DROP'
                 % (interface, address))
    rules.append('FORWARD -p IPv4 -i %s --ip-protocol udp '
                 '--ip-destination-port 67:68 -j DROP'
                 % interface)
    rules.append('FORWARD -p IPv4 -o %s --ip-protocol udp '
                 '--ip-destination-port 67:68 -j DROP'
                 % interface)
    # NOTE(vish): the above is not possible with iptables/arptables
    ensure_ebtables_rules(rules)


def remove_isolate_dhcp_address(interface, address):
    # block arp traffic to address across the interface
    rules = []
    rules.append('INPUT -p ARP -i %s --arp-ip-dst %s -j DROP'
                 % (interface, address))
    rules.append('OUTPUT -p ARP -o %s --arp-ip-src %s -j DROP'
                 % (interface, address))
    rules.append('FORWARD -p IPv4 -i %s --ip-protocol udp '
                 '--ip-destination-port 67:68 -j DROP'
                 % interface)
    rules.append('FORWARD -p IPv4 -o %s --ip-protocol udp '
                 '--ip-destination-port 67:68 -j DROP'
                 % interface)
    remove_ebtables_rules(rules)
    # NOTE(vish): the above is not possible with iptables/arptables


def get_gateway_rules(bridge):
    interfaces = CONF.forward_bridge_interface
    if 'all' in interfaces:
        return [('FORWARD', '-i %s -j ACCEPT' % bridge),
                ('FORWARD', '-o %s -j ACCEPT' % bridge)]
    rules = []
    for iface in CONF.forward_bridge_interface:
        if iface:
            rules.append(('FORWARD', '-i %s -o %s -j ACCEPT' % (bridge,
                                                                iface)))
            rules.append(('FORWARD', '-i %s -o %s -j ACCEPT' % (iface,
                                                                bridge)))
    rules.append(('FORWARD', '-i %s -o %s -j ACCEPT' % (bridge, bridge)))
    rules.append(('FORWARD', '-i %s -j %s' % (bridge,
                                              CONF.iptables_drop_action)))
    rules.append(('FORWARD', '-o %s -j %s' % (bridge,
                                              CONF.iptables_drop_action)))
    return rules


# plugs interfaces using Open vSwitch
class LinuxOVSInterfaceDriver(LinuxNetInterfaceDriver):

    def plug(self, network, mac_address, gateway=True):
        dev = self.get_dev(network)
        if not device_exists(dev):
            bridge = CONF.linuxnet_ovs_integration_bridge
            _ovs_vsctl(['--', '--may-exist', 'add-port', bridge, dev,
                        '--', 'set', 'Interface', dev, 'type=internal',
                        '--', 'set', 'Interface', dev,
                        'external-ids:iface-id=%s' % dev,
                        '--', 'set', 'Interface', dev,
                        'external-ids:iface-status=active',
                        '--', 'set', 'Interface', dev,
                        'external-ids:attached-mac=%s' % mac_address])
            _execute('ip', 'link', 'set', dev, 'address', mac_address,
                     run_as_root=True)
            _set_device_mtu(dev, network.get('mtu'))
            _execute('ip', 'link', 'set', dev, 'up', run_as_root=True)
            if not gateway:
                # If we weren't instructed to act as a gateway then add the
                # appropriate flows to block all non-dhcp traffic.
                _execute('ovs-ofctl',
                         'add-flow', bridge, 'priority=1,actions=drop',
                         run_as_root=True)
                _execute('ovs-ofctl', 'add-flow', bridge,
                         'udp,tp_dst=67,dl_dst=%s,priority=2,actions=normal' %
                         mac_address, run_as_root=True)
                # .. and make sure iptbles won't forward it as well.
                iptables_manager.ipv4['filter'].add_rule('FORWARD',
                    '--in-interface %s -j %s' % (bridge,
                                                 CONF.iptables_drop_action))
                iptables_manager.ipv4['filter'].add_rule('FORWARD',
                    '--out-interface %s -j %s' % (bridge,
                                                  CONF.iptables_drop_action))
            else:
                for rule in get_gateway_rules(bridge):
                    iptables_manager.ipv4['filter'].add_rule(*rule)

        return dev

    def unplug(self, network):
        dev = self.get_dev(network)
        bridge = CONF.linuxnet_ovs_integration_bridge
        _ovs_vsctl(['--', '--if-exists', 'del-port', bridge, dev])
        return dev

    def get_dev(self, network):
        dev = 'gw-' + str(network['uuid'][0:11])
        return dev


# plugs interfaces using Linux Bridge when using NeutronManager
class NeutronLinuxBridgeInterfaceDriver(LinuxNetInterfaceDriver):

    BRIDGE_NAME_PREFIX = 'brq'
    GATEWAY_INTERFACE_PREFIX = 'gw-'

    def plug(self, network, mac_address, gateway=True):
        dev = self.get_dev(network)
        bridge = self.get_bridge(network)
        if not gateway:
            # If we weren't instructed to act as a gateway then add the
            # appropriate flows to block all non-dhcp traffic.
            # .. and make sure iptbles won't forward it as well.
            iptables_manager.ipv4['filter'].add_rule('FORWARD',
                    ('--in-interface %s -j %s'
                     % (bridge, CONF.iptables_drop_action)))
            iptables_manager.ipv4['filter'].add_rule('FORWARD',
                    ('--out-interface %s -j %s'
                     % (bridge, CONF.iptables_drop_action)))
            return bridge
        else:
            for rule in get_gateway_rules(bridge):
                iptables_manager.ipv4['filter'].add_rule(*rule)

        create_tap_dev(dev, mac_address)

        if not device_exists(bridge):
            LOG.debug("Starting bridge %s ", bridge)
            utils.execute('brctl', 'addbr', bridge, run_as_root=True)
            utils.execute('brctl', 'setfd', bridge, str(0), run_as_root=True)
            utils.execute('brctl', 'stp', bridge, 'off', run_as_root=True)
            utils.execute('ip', 'link', 'set', bridge, 'address', mac_address,
                          run_as_root=True, check_exit_code=[0, 2, 254])
            utils.execute('ip', 'link', 'set', bridge, 'up', run_as_root=True,
                          check_exit_code=[0, 2, 254])
            LOG.debug("Done starting bridge %s", bridge)

            full_ip = '%s/%s' % (network['dhcp_server'],
                                 network['cidr'].rpartition('/')[2])
            utils.execute('ip', 'address', 'add', full_ip, 'dev', bridge,
                          run_as_root=True, check_exit_code=[0, 2, 254])

        return dev

    def unplug(self, network):
        dev = self.get_dev(network)
        if not device_exists(dev):
            return None
        else:
            delete_net_dev(dev)
            return dev

    def get_dev(self, network):
        dev = self.GATEWAY_INTERFACE_PREFIX + str(network['uuid'][0:11])
        return dev

    def get_bridge(self, network):
        bridge = self.BRIDGE_NAME_PREFIX + str(network['uuid'][0:11])
        return bridge

# provide compatibility with existing configs
QuantumLinuxBridgeInterfaceDriver = NeutronLinuxBridgeInterfaceDriver

iptables_manager = IptablesManager()
