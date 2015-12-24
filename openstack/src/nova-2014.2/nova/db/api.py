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

"""Defines interface for DB access.

Functions in this module are imported into the nova.db namespace. Call these
functions from nova.db namespace, not the nova.db.api namespace.

All functions in this module return objects that implement a dictionary-like
interface. Currently, many of these objects are sqlalchemy objects that
implement a dictionary interface. However, a future goal is to have all of
these objects be simple dictionaries.

"""

from oslo.config import cfg
from oslo.db import concurrency

from nova.cells import rpcapi as cells_rpcapi
from nova.i18n import _
from nova.openstack.common import log as logging


db_opts = [
    cfg.BoolOpt('enable_new_services',
                default=True,
                help='Services to be added to the available pool on create'),
    cfg.StrOpt('instance_name_template',
               default='instance-%08x',
               help='Template string to be used to generate instance names'),
    cfg.StrOpt('snapshot_name_template',
               default='snapshot-%s',
               help='Template string to be used to generate snapshot names'),
]

CONF = cfg.CONF
CONF.register_opts(db_opts)

_BACKEND_MAPPING = {'sqlalchemy': 'nova.db.sqlalchemy.api'}


IMPL = concurrency.TpoolDbapiWrapper(CONF, backend_mapping=_BACKEND_MAPPING)

LOG = logging.getLogger(__name__)

# The maximum value a signed INT type may have
MAX_INT = 0x7FFFFFFF

###################


def constraint(**conditions):
    """Return a constraint object suitable for use with some updates."""
    return IMPL.constraint(**conditions)


def equal_any(*values):
    """Return an equality condition object suitable for use in a constraint.

    Equal_any conditions require that a model object's attribute equal any
    one of the given values.
    """
    return IMPL.equal_any(*values)


def not_equal(*values):
    """Return an inequality condition object suitable for use in a constraint.

    Not_equal conditions require that a model object's attribute differs from
    all of the given values.
    """
    return IMPL.not_equal(*values)


###################


def service_destroy(context, service_id):
    """Destroy the service or raise if it does not exist."""
    return IMPL.service_destroy(context, service_id)


def service_get(context, service_id, with_compute_node=False,
                use_slave=False):
    """Get a service or raise if it does not exist."""
    return IMPL.service_get(context, service_id,
                            with_compute_node=with_compute_node,
                            use_slave=use_slave)


def service_get_by_host_and_topic(context, host, topic):
    """Get a service by host it's on and topic it listens to."""
    return IMPL.service_get_by_host_and_topic(context, host, topic)


def service_get_all(context, disabled=None):
    """Get all services."""
    return IMPL.service_get_all(context, disabled)


def service_get_all_by_topic(context, topic):
    """Get all services for a given topic."""
    return IMPL.service_get_all_by_topic(context, topic)


def service_get_all_by_host(context, host):
    """Get all services for a given host."""
    return IMPL.service_get_all_by_host(context, host)


def service_get_by_compute_host(context, host, use_slave=False):
    """Get the service entry for a given compute host.

    Returns the service entry joined with the compute_node entry.
    """
    return IMPL.service_get_by_compute_host(context, host,
                                            use_slave=use_slave)


def service_get_by_args(context, host, binary):
    """Get the state of a service by node name and binary."""
    return IMPL.service_get_by_args(context, host, binary)


def service_create(context, values):
    """Create a service from the values dictionary."""
    return IMPL.service_create(context, values)


def service_update(context, service_id, values):
    """Set the given properties on a service and update it.

    Raises NotFound if service does not exist.

    """
    return IMPL.service_update(context, service_id, values)


###################


def compute_node_get(context, compute_id):
    """Get a compute node by its id.

    :param context: The security context
    :param compute_id: ID of the compute node

    :returns: Dictionary-like object containing properties of the compute node,
              including its corresponding service

    Raises ComputeHostNotFound if compute node with the given ID doesn't exist.
    """
    return IMPL.compute_node_get(context, compute_id)


def compute_node_get_by_service_id(context, service_id):
    """Get a compute node by its associated service id.

    :param context: The security context
    :param service_id: ID of the associated service

    :returns: Dictionary-like object containing properties of the compute node,
              including its corresponding service and statistics

    Raises ServiceNotFound if service with the given ID doesn't exist.
    """
    return IMPL.compute_node_get_by_service_id(context, service_id)


def compute_node_get_all(context, no_date_fields=False):
    """Get all computeNodes.

    :param context: The security context
    :param no_date_fields: If set to True, excludes 'created_at', 'updated_at',
                           'deleted_at' and 'deleted' fields from the output,
                           thus significantly reducing its size.
                           Set to False by default

    :returns: List of dictionaries each containing compute node properties,
              including corresponding service
    """
    return IMPL.compute_node_get_all(context, no_date_fields)


def compute_node_search_by_hypervisor(context, hypervisor_match):
    """Get compute nodes by hypervisor hostname.

    :param context: The security context
    :param hypervisor_match: The hypervisor hostname

    :returns: List of dictionary-like objects each containing compute node
              properties, including corresponding service
    """
    return IMPL.compute_node_search_by_hypervisor(context, hypervisor_match)


def compute_node_create(context, values):
    """Create a compute node from the values dictionary.

    :param context: The security context
    :param values: Dictionary containing compute node properties

    :returns: Dictionary-like object containing the properties of the created
              node, including its corresponding service and statistics
    """
    return IMPL.compute_node_create(context, values)


def compute_node_update(context, compute_id, values):
    """Set the given properties on a compute node and update it.

    :param context: The security context
    :param compute_id: ID of the compute node
    :param values: Dictionary containing compute node properties to be updated

    :returns: Dictionary-like object containing the properties of the updated
              compute node, including its corresponding service and statistics

    Raises ComputeHostNotFound if compute node with the given ID doesn't exist.
    """
    return IMPL.compute_node_update(context, compute_id, values)


def compute_node_delete(context, compute_id):
    """Delete a compute node from the database.

    :param context: The security context
    :param compute_id: ID of the compute node

    Raises ComputeHostNotFound if compute node with the given ID doesn't exist.
    """
    return IMPL.compute_node_delete(context, compute_id)


def compute_node_statistics(context):
    """Get aggregate statistics over all compute nodes.

    :param context: The security context

    :returns: Dictionary containing compute node characteristics summed up
              over all the compute nodes, e.g. 'vcpus', 'free_ram_mb' etc.
    """
    return IMPL.compute_node_statistics(context)


###################


def certificate_create(context, values):
    """Create a certificate from the values dictionary."""
    return IMPL.certificate_create(context, values)


def certificate_get_all_by_project(context, project_id):
    """Get all certificates for a project."""
    return IMPL.certificate_get_all_by_project(context, project_id)


def certificate_get_all_by_user(context, user_id):
    """Get all certificates for a user."""
    return IMPL.certificate_get_all_by_user(context, user_id)


def certificate_get_all_by_user_and_project(context, user_id, project_id):
    """Get all certificates for a user and project."""
    return IMPL.certificate_get_all_by_user_and_project(context,
                                                        user_id,
                                                        project_id)


###################

def floating_ip_get(context, id):
    return IMPL.floating_ip_get(context, id)


def floating_ip_get_pools(context):
    """Returns a list of floating ip pools."""
    return IMPL.floating_ip_get_pools(context)


def floating_ip_allocate_address(context, project_id, pool,
                                 auto_assigned=False):
    """Allocate free floating ip from specified pool and return the address.

    Raises if one is not available.

    """
    return IMPL.floating_ip_allocate_address(context, project_id, pool,
                                             auto_assigned)


def floating_ip_bulk_create(context, ips):
    """Create a lot of floating ips from the values dictionary."""
    return IMPL.floating_ip_bulk_create(context, ips)


def floating_ip_bulk_destroy(context, ips):
    """Destroy a lot of floating ips from the values dictionary."""
    return IMPL.floating_ip_bulk_destroy(context, ips)


def floating_ip_create(context, values):
    """Create a floating ip from the values dictionary."""
    return IMPL.floating_ip_create(context, values)


def floating_ip_deallocate(context, address):
    """Deallocate a floating ip by address."""
    return IMPL.floating_ip_deallocate(context, address)


def floating_ip_destroy(context, address):
    """Destroy the floating_ip or raise if it does not exist."""
    return IMPL.floating_ip_destroy(context, address)


def floating_ip_disassociate(context, address):
    """Disassociate a floating ip from a fixed ip by address.

    :returns: the fixed ip record joined to network record or None
              if the ip was not associated to an ip.

    """
    return IMPL.floating_ip_disassociate(context, address)


def floating_ip_fixed_ip_associate(context, floating_address,
                                   fixed_address, host):
    """Associate a floating ip to a fixed_ip by address.

    :returns: the fixed ip record joined to network record or None
              if the ip was already associated to the fixed ip.
    """

    return IMPL.floating_ip_fixed_ip_associate(context,
                                               floating_address,
                                               fixed_address,
                                               host)


def floating_ip_get_all(context):
    """Get all floating ips."""
    return IMPL.floating_ip_get_all(context)


def floating_ip_get_all_by_host(context, host):
    """Get all floating ips by host."""
    return IMPL.floating_ip_get_all_by_host(context, host)


def floating_ip_get_all_by_project(context, project_id):
    """Get all floating ips by project."""
    return IMPL.floating_ip_get_all_by_project(context, project_id)


def floating_ip_get_by_address(context, address):
    """Get a floating ip by address or raise if it doesn't exist."""
    return IMPL.floating_ip_get_by_address(context, address)


def floating_ip_get_by_fixed_address(context, fixed_address):
    """Get a floating ips by fixed address."""
    return IMPL.floating_ip_get_by_fixed_address(context, fixed_address)


def floating_ip_get_by_fixed_ip_id(context, fixed_ip_id):
    """Get a floating ips by fixed address."""
    return IMPL.floating_ip_get_by_fixed_ip_id(context, fixed_ip_id)


def floating_ip_update(context, address, values):
    """Update a floating ip by address or raise if it doesn't exist."""
    return IMPL.floating_ip_update(context, address, values)


def floating_ip_set_auto_assigned(context, address):
    """Set auto_assigned flag to floating ip."""
    return IMPL.floating_ip_set_auto_assigned(context, address)


def dnsdomain_list(context):
    """Get a list of all zones in our database, public and private."""
    return IMPL.dnsdomain_list(context)


def dnsdomain_get_all(context):
    """Get a list of all dnsdomains in our database."""
    return IMPL.dnsdomain_get_all(context)


def dnsdomain_register_for_zone(context, fqdomain, zone):
    """Associated a DNS domain with an availability zone."""
    return IMPL.dnsdomain_register_for_zone(context, fqdomain, zone)


def dnsdomain_register_for_project(context, fqdomain, project):
    """Associated a DNS domain with a project id."""
    return IMPL.dnsdomain_register_for_project(context, fqdomain, project)


def dnsdomain_unregister(context, fqdomain):
    """Purge associations for the specified DNS zone."""
    return IMPL.dnsdomain_unregister(context, fqdomain)


def dnsdomain_get(context, fqdomain):
    """Get the db record for the specified domain."""
    return IMPL.dnsdomain_get(context, fqdomain)


####################


def migration_update(context, id, values):
    """Update a migration instance."""
    return IMPL.migration_update(context, id, values)


def migration_create(context, values):
    """Create a migration record."""
    return IMPL.migration_create(context, values)


def migration_get(context, migration_id):
    """Finds a migration by the id."""
    return IMPL.migration_get(context, migration_id)


def migration_get_by_instance_and_status(context, instance_uuid, status):
    """Finds a migration by the instance uuid its migrating."""
    return IMPL.migration_get_by_instance_and_status(context, instance_uuid,
            status)


def migration_get_unconfirmed_by_dest_compute(context, confirm_window,
        dest_compute, use_slave=False):
    """Finds all unconfirmed migrations within the confirmation window for
    a specific destination compute host.
    """
    return IMPL.migration_get_unconfirmed_by_dest_compute(context,
            confirm_window, dest_compute, use_slave=use_slave)


def migration_get_in_progress_by_host_and_node(context, host, node):
    """Finds all migrations for the given host + node  that are not yet
    confirmed or reverted.
    """
    return IMPL.migration_get_in_progress_by_host_and_node(context, host, node)


def migration_get_all_by_filters(context, filters):
    """Finds all migrations in progress."""
    return IMPL.migration_get_all_by_filters(context, filters)


####################


def fixed_ip_associate(context, address, instance_uuid, network_id=None,
                       reserved=False):
    """Associate fixed ip to instance.

    Raises if fixed ip is not available.

    """
    return IMPL.fixed_ip_associate(context, address, instance_uuid, network_id,
                                   reserved)


def fixed_ip_associate_pool(context, network_id, instance_uuid=None,
                            host=None):
    """Find free ip in network and associate it to instance or host.

    Raises if one is not available.

    """
    return IMPL.fixed_ip_associate_pool(context, network_id,
                                        instance_uuid, host)


def fixed_ip_create(context, values):
    """Create a fixed ip from the values dictionary."""
    return IMPL.fixed_ip_create(context, values)


def fixed_ip_bulk_create(context, ips):
    """Create a lot of fixed ips from the values dictionary."""
    return IMPL.fixed_ip_bulk_create(context, ips)


def fixed_ip_disassociate(context, address):
    """Disassociate a fixed ip from an instance by address."""
    return IMPL.fixed_ip_disassociate(context, address)


def fixed_ip_disassociate_all_by_timeout(context, host, time):
    """Disassociate old fixed ips from host."""
    return IMPL.fixed_ip_disassociate_all_by_timeout(context, host, time)


def fixed_ip_get(context, id, get_network=False):
    """Get fixed ip by id or raise if it does not exist.

    If get_network is true, also return the associated network.
    """
    return IMPL.fixed_ip_get(context, id, get_network)


def fixed_ip_get_all(context):
    """Get all defined fixed ips."""
    return IMPL.fixed_ip_get_all(context)


def fixed_ip_get_by_address(context, address, columns_to_join=None):
    """Get a fixed ip by address or raise if it does not exist."""
    return IMPL.fixed_ip_get_by_address(context, address,
                                        columns_to_join=columns_to_join)


def fixed_ip_get_by_address_detailed(context, address):
    """Get detailed fixed ip info by address or raise if it does not exist."""
    return IMPL.fixed_ip_get_by_address_detailed(context, address)


def fixed_ip_get_by_floating_address(context, floating_address):
    """Get a fixed ip by a floating address."""
    return IMPL.fixed_ip_get_by_floating_address(context, floating_address)


def fixed_ip_get_by_instance(context, instance_uuid):
    """Get fixed ips by instance or raise if none exist."""
    return IMPL.fixed_ip_get_by_instance(context, instance_uuid)


def fixed_ip_get_by_host(context, host):
    """Get fixed ips by compute host."""
    return IMPL.fixed_ip_get_by_host(context, host)


def fixed_ip_get_by_network_host(context, network_uuid, host):
    """Get fixed ip for a host in a network."""
    return IMPL.fixed_ip_get_by_network_host(context, network_uuid, host)


def fixed_ips_by_virtual_interface(context, vif_id):
    """Get fixed ips by virtual interface or raise if none exist."""
    return IMPL.fixed_ips_by_virtual_interface(context, vif_id)


def fixed_ip_update(context, address, values):
    """Create a fixed ip from the values dictionary."""
    return IMPL.fixed_ip_update(context, address, values)


####################


def virtual_interface_create(context, values):
    """Create a virtual interface record in the database."""
    return IMPL.virtual_interface_create(context, values)


def virtual_interface_get(context, vif_id):
    """Gets a virtual interface from the table."""
    return IMPL.virtual_interface_get(context, vif_id)


def virtual_interface_get_by_address(context, address):
    """Gets a virtual interface from the table filtering on address."""
    return IMPL.virtual_interface_get_by_address(context, address)


def virtual_interface_get_by_uuid(context, vif_uuid):
    """Gets a virtual interface from the table filtering on vif uuid."""
    return IMPL.virtual_interface_get_by_uuid(context, vif_uuid)


def virtual_interface_get_by_instance(context, instance_id, use_slave=False):
    """Gets all virtual_interfaces for instance."""
    return IMPL.virtual_interface_get_by_instance(context, instance_id,
                                                  use_slave=use_slave)


def virtual_interface_get_by_instance_and_network(context, instance_id,
                                                           network_id):
    """Gets all virtual interfaces for instance."""
    return IMPL.virtual_interface_get_by_instance_and_network(context,
                                                              instance_id,
                                                              network_id)


def virtual_interface_delete_by_instance(context, instance_id):
    """Delete virtual interface records associated with instance."""
    return IMPL.virtual_interface_delete_by_instance(context, instance_id)


def virtual_interface_get_all(context):
    """Gets all virtual interfaces from the table."""
    return IMPL.virtual_interface_get_all(context)


####################


def instance_create(context, values):
    """Create an instance from the values dictionary."""
    return IMPL.instance_create(context, values)


def instance_destroy(context, instance_uuid, constraint=None,
        update_cells=True):
    """Destroy the instance or raise if it does not exist."""
    rv = IMPL.instance_destroy(context, instance_uuid, constraint)
    if update_cells:
        try:
            cells_rpcapi.CellsAPI().instance_destroy_at_top(context, rv)
        except Exception:
            LOG.exception(_("Failed to notify cells of instance destroy"))
    return rv


def instance_get_by_uuid(context, uuid, columns_to_join=None, use_slave=False):
    """Get an instance or raise if it does not exist."""
    return IMPL.instance_get_by_uuid(context, uuid,
                                     columns_to_join, use_slave=use_slave)


def instance_get(context, instance_id, columns_to_join=None):
    """Get an instance or raise if it does not exist."""
    return IMPL.instance_get(context, instance_id,
                             columns_to_join=columns_to_join)


def instance_get_all(context, columns_to_join=None):
    """Get all instances."""
    return IMPL.instance_get_all(context, columns_to_join=columns_to_join)


def instance_get_all_by_filters(context, filters, sort_key='created_at',
                                sort_dir='desc', limit=None, marker=None,
                                columns_to_join=None, use_slave=False):
    """Get all instances that match all filters."""
    return IMPL.instance_get_all_by_filters(context, filters, sort_key,
                                            sort_dir, limit=limit,
                                            marker=marker,
                                            columns_to_join=columns_to_join,
                                            use_slave=use_slave)


def instance_get_active_by_window_joined(context, begin, end=None,
                                         project_id=None, host=None,
                                         use_slave=False):
    """Get instances and joins active during a certain time window.

    Specifying a project_id will filter for a certain project.
    Specifying a host will filter for instances on a given compute host.
    """
    return IMPL.instance_get_active_by_window_joined(context, begin, end,
                                              project_id, host,
                                              use_slave=use_slave)


def instance_get_all_by_host(context, host,
                             columns_to_join=None, use_slave=False):
    """Get all instances belonging to a host."""
    return IMPL.instance_get_all_by_host(context, host,
                                         columns_to_join,
                                         use_slave=use_slave)


def instance_get_all_by_host_and_node(context, host, node):
    """Get all instances belonging to a node."""
    return IMPL.instance_get_all_by_host_and_node(context, host, node)


def instance_get_all_by_host_and_not_type(context, host, type_id=None):
    """Get all instances belonging to a host with a different type_id."""
    return IMPL.instance_get_all_by_host_and_not_type(context, host, type_id)


def instance_get_floating_address(context, instance_id):
    """Get the first floating ip address of an instance."""
    return IMPL.instance_get_floating_address(context, instance_id)


def instance_floating_address_get_all(context, instance_uuid):
    """Get all floating ip addresses of an instance."""
    return IMPL.instance_floating_address_get_all(context, instance_uuid)


# NOTE(hanlind): This method can be removed as conductor RPC API moves to v2.0.
def instance_get_all_hung_in_rebooting(context, reboot_window):
    """Get all instances stuck in a rebooting state."""
    return IMPL.instance_get_all_hung_in_rebooting(context, reboot_window)


def instance_update(context, instance_uuid, values, update_cells=True):
    """Set the given properties on an instance and update it.

    Raises NotFound if instance does not exist.

    """
    rv = IMPL.instance_update(context, instance_uuid, values)
    if update_cells:
        try:
            cells_rpcapi.CellsAPI().instance_update_at_top(context, rv)
        except Exception:
            LOG.exception(_("Failed to notify cells of instance update"))
    return rv


# FIXME(comstud): 'update_cells' is temporary as we transition to using
# objects.  When everything is using Instance.save(), we can remove the
# argument and the RPC to nova-cells.
def instance_update_and_get_original(context, instance_uuid, values,
                                     update_cells=True,
                                     columns_to_join=None):
    """Set the given properties on an instance and update it. Return
    a shallow copy of the original instance reference, as well as the
    updated one.

    :param context: = request context object
    :param instance_uuid: = instance id or uuid
    :param values: = dict containing column values

    :returns: a tuple of the form (old_instance_ref, new_instance_ref)

    Raises NotFound if instance does not exist.
    """
    rv = IMPL.instance_update_and_get_original(context, instance_uuid, values,
                                               columns_to_join=columns_to_join)
    if update_cells:
        try:
            cells_rpcapi.CellsAPI().instance_update_at_top(context, rv[1])
        except Exception:
            LOG.exception(_("Failed to notify cells of instance update"))
    return rv


def instance_add_security_group(context, instance_id, security_group_id):
    """Associate the given security group with the given instance."""
    return IMPL.instance_add_security_group(context, instance_id,
                                            security_group_id)


def instance_remove_security_group(context, instance_id, security_group_id):
    """Disassociate the given security group from the given instance."""
    return IMPL.instance_remove_security_group(context, instance_id,
                                            security_group_id)


####################


def instance_group_create(context, values, policies=None, members=None):
    """Create a new group.

    Each group will receive a unique uuid. This will be used for access to the
    group.
    """
    return IMPL.instance_group_create(context, values, policies, members)


def instance_group_get(context, group_uuid):
    """Get a specific group by id."""
    return IMPL.instance_group_get(context, group_uuid)


def instance_group_update(context, group_uuid, values):
    """Update the attributes of an group."""
    return IMPL.instance_group_update(context, group_uuid, values)


def instance_group_delete(context, group_uuid):
    """Delete an group."""
    return IMPL.instance_group_delete(context, group_uuid)


def instance_group_get_all(context):
    """Get all groups."""
    return IMPL.instance_group_get_all(context)


def instance_group_get_all_by_project_id(context, project_id):
    """Get all groups for a specific project_id."""
    return IMPL.instance_group_get_all_by_project_id(context, project_id)


def instance_group_metadata_add(context, group_uuid, metadata,
                                set_delete=False):
    """Add metadata to the group."""
    return IMPL.instance_group_metadata_add(context, group_uuid, metadata,
                                            set_delete)


def instance_group_metadata_delete(context, group_uuid, key):
    """Delete metadata from the group."""
    return IMPL.instance_group_metadata_delete(context, group_uuid, key)


def instance_group_metadata_get(context, group_uuid):
    """Get the metadata from the group."""
    return IMPL.instance_group_metadata_get(context, group_uuid)


def instance_group_members_add(context, group_uuid, members,
                               set_delete=False):
    """Add members to the group."""
    return IMPL.instance_group_members_add(context, group_uuid, members,
                                           set_delete=set_delete)


def instance_group_member_delete(context, group_uuid, instance_id):
    """Delete a specific member from the group."""
    return IMPL.instance_group_member_delete(context, group_uuid, instance_id)


def instance_group_members_get(context, group_uuid):
    """Get the members from the group."""
    return IMPL.instance_group_members_get(context, group_uuid)


def instance_group_policies_add(context, group_uuid, policies,
                                set_delete=False):
    """Add policies to the group."""
    return IMPL.instance_group_policies_add(context, group_uuid, policies,
                                            set_delete=set_delete)


def instance_group_policy_delete(context, group_uuid, policy):
    """Delete a specific policy from the group."""
    return IMPL.instance_group_policy_delete(context, group_uuid, policy)


def instance_group_policies_get(context, group_uuid):
    """Get the policies from the group."""
    return IMPL.instance_group_policies_get(context, group_uuid)


###################


def instance_info_cache_get(context, instance_uuid):
    """Gets an instance info cache from the table.

    :param instance_uuid: = uuid of the info cache's instance
    """
    return IMPL.instance_info_cache_get(context, instance_uuid)


def instance_info_cache_update(context, instance_uuid, values):
    """Update an instance info cache record in the table.

    :param instance_uuid: = uuid of info cache's instance
    :param values: = dict containing column values to update
    """
    return IMPL.instance_info_cache_update(context, instance_uuid, values)


def instance_info_cache_delete(context, instance_uuid):
    """Deletes an existing instance_info_cache record

    :param instance_uuid: = uuid of the instance tied to the cache record
    """
    return IMPL.instance_info_cache_delete(context, instance_uuid)


###################


def instance_extra_get_by_instance_uuid(context, instance_uuid):
    """Get the instance extra record

    :param instance_uuid: = uuid of the instance tied to the topology record
    """
    return IMPL.instance_extra_get_by_instance_uuid(context, instance_uuid)


def instance_extra_update_by_uuid(context, instance_uuid, updates):
    """Update the instance extra record by instance uuid

    :param instance_uuid: = uuid of the instance tied to the record
    :param updates: A dict of updates to apply
    """
    return IMPL.instance_extra_update_by_uuid(context, instance_uuid,
                                              updates)


###################


def key_pair_create(context, values):
    """Create a key_pair from the values dictionary."""
    return IMPL.key_pair_create(context, values)


def key_pair_destroy(context, user_id, name):
    """Destroy the key_pair or raise if it does not exist."""
    return IMPL.key_pair_destroy(context, user_id, name)


def key_pair_get(context, user_id, name):
    """Get a key_pair or raise if it does not exist."""
    return IMPL.key_pair_get(context, user_id, name)


def key_pair_get_all_by_user(context, user_id):
    """Get all key_pairs by user."""
    return IMPL.key_pair_get_all_by_user(context, user_id)


def key_pair_count_by_user(context, user_id):
    """Count number of key pairs for the given user ID."""
    return IMPL.key_pair_count_by_user(context, user_id)


####################


def network_associate(context, project_id, network_id=None, force=False):
    """Associate a free network to a project."""
    return IMPL.network_associate(context, project_id, network_id, force)


def network_count_reserved_ips(context, network_id):
    """Return the number of reserved ips in the network."""
    return IMPL.network_count_reserved_ips(context, network_id)


def network_create_safe(context, values):
    """Create a network from the values dict.

    The network is only returned if the create succeeds. If the create violates
    constraints because the network already exists, no exception is raised.

    """
    return IMPL.network_create_safe(context, values)


def network_delete_safe(context, network_id):
    """Delete network with key network_id.

    This method assumes that the network is not associated with any project

    """
    return IMPL.network_delete_safe(context, network_id)


def network_disassociate(context, network_id, disassociate_host=True,
                         disassociate_project=True):
    """Disassociate the network from project or host

    Raises if it does not exist.
    """
    return IMPL.network_disassociate(context, network_id, disassociate_host,
                                     disassociate_project)


def network_get(context, network_id, project_only="allow_none"):
    """Get a network or raise if it does not exist."""
    return IMPL.network_get(context, network_id, project_only=project_only)


def network_get_all(context, project_only="allow_none"):
    """Return all defined networks."""
    return IMPL.network_get_all(context, project_only)


def network_get_all_by_uuids(context, network_uuids,
                             project_only="allow_none"):
    """Return networks by ids."""
    return IMPL.network_get_all_by_uuids(context, network_uuids,
                                         project_only=project_only)


# pylint: disable=C0103

def network_in_use_on_host(context, network_id, host=None):
    """Indicates if a network is currently in use on host."""
    return IMPL.network_in_use_on_host(context, network_id, host)


def network_get_associated_fixed_ips(context, network_id, host=None):
    """Get all network's ips that have been associated."""
    return IMPL.network_get_associated_fixed_ips(context, network_id, host)


def network_get_by_uuid(context, uuid):
    """Get a network by uuid or raise if it does not exist."""
    return IMPL.network_get_by_uuid(context, uuid)


def network_get_by_cidr(context, cidr):
    """Get a network by cidr or raise if it does not exist."""
    return IMPL.network_get_by_cidr(context, cidr)


def network_get_all_by_host(context, host):
    """All networks for which the given host is the network host."""
    return IMPL.network_get_all_by_host(context, host)


def network_set_host(context, network_id, host_id):
    """Safely set the host for network."""
    return IMPL.network_set_host(context, network_id, host_id)


def network_update(context, network_id, values):
    """Set the given properties on a network and update it.

    Raises NotFound if network does not exist.

    """
    return IMPL.network_update(context, network_id, values)


###############


def quota_create(context, project_id, resource, limit, user_id=None):
    """Create a quota for the given project and resource."""
    return IMPL.quota_create(context, project_id, resource, limit,
                             user_id=user_id)


def quota_get(context, project_id, resource, user_id=None):
    """Retrieve a quota or raise if it does not exist."""
    return IMPL.quota_get(context, project_id, resource, user_id=user_id)


def quota_get_all_by_project_and_user(context, project_id, user_id):
    """Retrieve all quotas associated with a given project and user."""
    return IMPL.quota_get_all_by_project_and_user(context, project_id, user_id)


def quota_get_all_by_project(context, project_id):
    """Retrieve all quotas associated with a given project."""
    return IMPL.quota_get_all_by_project(context, project_id)


def quota_get_all(context, project_id):
    """Retrieve all user quotas associated with a given project."""
    return IMPL.quota_get_all(context, project_id)


def quota_update(context, project_id, resource, limit, user_id=None):
    """Update a quota or raise if it does not exist."""
    return IMPL.quota_update(context, project_id, resource, limit,
                             user_id=user_id)


###################


def quota_class_create(context, class_name, resource, limit):
    """Create a quota class for the given name and resource."""
    return IMPL.quota_class_create(context, class_name, resource, limit)


def quota_class_get(context, class_name, resource):
    """Retrieve a quota class or raise if it does not exist."""
    return IMPL.quota_class_get(context, class_name, resource)


def quota_class_get_default(context):
    """Retrieve all default quotas."""
    return IMPL.quota_class_get_default(context)


def quota_class_get_all_by_name(context, class_name):
    """Retrieve all quotas associated with a given quota class."""
    return IMPL.quota_class_get_all_by_name(context, class_name)


def quota_class_update(context, class_name, resource, limit):
    """Update a quota class or raise if it does not exist."""
    return IMPL.quota_class_update(context, class_name, resource, limit)


###################


def quota_usage_get(context, project_id, resource, user_id=None):
    """Retrieve a quota usage or raise if it does not exist."""
    return IMPL.quota_usage_get(context, project_id, resource, user_id=user_id)


def quota_usage_get_all_by_project_and_user(context, project_id, user_id):
    """Retrieve all usage associated with a given resource."""
    return IMPL.quota_usage_get_all_by_project_and_user(context,
                                                        project_id, user_id)


def quota_usage_get_all_by_project(context, project_id):
    """Retrieve all usage associated with a given resource."""
    return IMPL.quota_usage_get_all_by_project(context, project_id)


def quota_usage_update(context, project_id, user_id, resource, **kwargs):
    """Update a quota usage or raise if it does not exist."""
    return IMPL.quota_usage_update(context, project_id, user_id, resource,
                                   **kwargs)


###################


def quota_reserve(context, resources, quotas, user_quotas, deltas, expire,
                  until_refresh, max_age, project_id=None, user_id=None):
    """Check quotas and create appropriate reservations."""
    return IMPL.quota_reserve(context, resources, quotas, user_quotas, deltas,
                              expire, until_refresh, max_age,
                              project_id=project_id, user_id=user_id)


def reservation_commit(context, reservations, project_id=None, user_id=None):
    """Commit quota reservations."""
    return IMPL.reservation_commit(context, reservations,
                                   project_id=project_id,
                                   user_id=user_id)


def reservation_rollback(context, reservations, project_id=None, user_id=None):
    """Roll back quota reservations."""
    return IMPL.reservation_rollback(context, reservations,
                                     project_id=project_id,
                                     user_id=user_id)


def quota_destroy_all_by_project_and_user(context, project_id, user_id):
    """Destroy all quotas associated with a given project and user."""
    return IMPL.quota_destroy_all_by_project_and_user(context,
                                                      project_id, user_id)


def quota_destroy_all_by_project(context, project_id):
    """Destroy all quotas associated with a given project."""
    return IMPL.quota_destroy_all_by_project(context, project_id)


def reservation_expire(context):
    """Roll back any expired reservations."""
    return IMPL.reservation_expire(context)


###################


def ec2_volume_create(context, volume_id, forced_id=None):
    return IMPL.ec2_volume_create(context, volume_id, forced_id)


def ec2_volume_get_by_id(context, volume_id):
    return IMPL.ec2_volume_get_by_id(context, volume_id)


def ec2_volume_get_by_uuid(context, volume_uuid):
    return IMPL.ec2_volume_get_by_uuid(context, volume_uuid)


def ec2_snapshot_create(context, snapshot_id, forced_id=None):
    return IMPL.ec2_snapshot_create(context, snapshot_id, forced_id)


def ec2_snapshot_get_by_ec2_id(context, ec2_id):
    return IMPL.ec2_snapshot_get_by_ec2_id(context, ec2_id)


def ec2_snapshot_get_by_uuid(context, snapshot_uuid):
    return IMPL.ec2_snapshot_get_by_uuid(context, snapshot_uuid)


####################


def block_device_mapping_create(context, values, legacy=True):
    """Create an entry of block device mapping."""
    return IMPL.block_device_mapping_create(context, values, legacy)


def block_device_mapping_update(context, bdm_id, values, legacy=True):
    """Update an entry of block device mapping."""
    return IMPL.block_device_mapping_update(context, bdm_id, values, legacy)


def block_device_mapping_update_or_create(context, values, legacy=True):
    """Update an entry of block device mapping.

    If not existed, create a new entry
    """
    return IMPL.block_device_mapping_update_or_create(context, values, legacy)


def block_device_mapping_get_all_by_instance(context, instance_uuid,
                                             use_slave=False):
    """Get all block device mapping belonging to an instance."""
    return IMPL.block_device_mapping_get_all_by_instance(context,
                                                         instance_uuid,
                                                         use_slave)


def block_device_mapping_get_by_volume_id(context, volume_id,
        columns_to_join=None):
    """Get block device mapping for a given volume."""
    return IMPL.block_device_mapping_get_by_volume_id(context, volume_id,
            columns_to_join)


def block_device_mapping_destroy(context, bdm_id):
    """Destroy the block device mapping."""
    return IMPL.block_device_mapping_destroy(context, bdm_id)


def block_device_mapping_destroy_by_instance_and_device(context, instance_uuid,
                                                        device_name):
    """Destroy the block device mapping."""
    return IMPL.block_device_mapping_destroy_by_instance_and_device(
        context, instance_uuid, device_name)


def block_device_mapping_destroy_by_instance_and_volume(context, instance_uuid,
                                                        volume_id):
    """Destroy the block device mapping."""
    return IMPL.block_device_mapping_destroy_by_instance_and_volume(
        context, instance_uuid, volume_id)


####################


def security_group_get_all(context):
    """Get all security groups."""
    return IMPL.security_group_get_all(context)


def security_group_get(context, security_group_id, columns_to_join=None):
    """Get security group by its id."""
    return IMPL.security_group_get(context, security_group_id,
                                   columns_to_join)


def security_group_get_by_name(context, project_id, group_name,
                               columns_to_join=None):
    """Returns a security group with the specified name from a project."""
    return IMPL.security_group_get_by_name(context, project_id, group_name,
                                           columns_to_join=None)


def security_group_get_by_project(context, project_id):
    """Get all security groups belonging to a project."""
    return IMPL.security_group_get_by_project(context, project_id)


def security_group_get_by_instance(context, instance_uuid):
    """Get security groups to which the instance is assigned."""
    return IMPL.security_group_get_by_instance(context, instance_uuid)


def security_group_in_use(context, group_id):
    """Indicates if a security group is currently in use."""
    return IMPL.security_group_in_use(context, group_id)


def security_group_create(context, values):
    """Create a new security group."""
    return IMPL.security_group_create(context, values)


def security_group_update(context, security_group_id, values,
                          columns_to_join=None):
    """Update a security group."""
    return IMPL.security_group_update(context, security_group_id, values,
                                      columns_to_join=columns_to_join)


def security_group_ensure_default(context):
    """Ensure default security group exists for a project_id.

    Returns a tuple with the first element being a bool indicating
    if the default security group previously existed. Second
    element is the dict used to create the default security group.
    """
    return IMPL.security_group_ensure_default(context)


def security_group_destroy(context, security_group_id):
    """Deletes a security group."""
    return IMPL.security_group_destroy(context, security_group_id)


####################


def security_group_rule_create(context, values):
    """Create a new security group."""
    return IMPL.security_group_rule_create(context, values)


def security_group_rule_get_by_security_group(context, security_group_id,
                                              columns_to_join=None):
    """Get all rules for a given security group."""
    return IMPL.security_group_rule_get_by_security_group(
        context, security_group_id, columns_to_join=columns_to_join)


def security_group_rule_get_by_security_group_grantee(context,
                                                      security_group_id):
    """Get all rules that grant access to the given security group."""
    return IMPL.security_group_rule_get_by_security_group_grantee(context,
                                                             security_group_id)


def security_group_rule_destroy(context, security_group_rule_id):
    """Deletes a security group rule."""
    return IMPL.security_group_rule_destroy(context, security_group_rule_id)


def security_group_rule_get(context, security_group_rule_id):
    """Gets a security group rule."""
    return IMPL.security_group_rule_get(context, security_group_rule_id)


def security_group_rule_count_by_group(context, security_group_id):
    """Count rules in a given security group."""
    return IMPL.security_group_rule_count_by_group(context, security_group_id)


###################


def security_group_default_rule_get(context, security_group_rule_default_id):
    return IMPL.security_group_default_rule_get(context,
                                                security_group_rule_default_id)


def security_group_default_rule_destroy(context,
                                        security_group_rule_default_id):
    return IMPL.security_group_default_rule_destroy(
        context, security_group_rule_default_id)


def security_group_default_rule_create(context, values):
    return IMPL.security_group_default_rule_create(context, values)


def security_group_default_rule_list(context):
    return IMPL.security_group_default_rule_list(context)


###################


def provider_fw_rule_create(context, rule):
    """Add a firewall rule at the provider level (all hosts & instances)."""
    return IMPL.provider_fw_rule_create(context, rule)


def provider_fw_rule_get_all(context):
    """Get all provider-level firewall rules."""
    return IMPL.provider_fw_rule_get_all(context)


def provider_fw_rule_destroy(context, rule_id):
    """Delete a provider firewall rule from the database."""
    return IMPL.provider_fw_rule_destroy(context, rule_id)


###################


def project_get_networks(context, project_id, associate=True):
    """Return the network associated with the project.

    If associate is true, it will attempt to associate a new
    network if one is not found, otherwise it returns None.

    """
    return IMPL.project_get_networks(context, project_id, associate)


###################


def console_pool_create(context, values):
    """Create console pool."""
    return IMPL.console_pool_create(context, values)


def console_pool_get_by_host_type(context, compute_host, proxy_host,
                                  console_type):
    """Fetch a console pool for a given proxy host, compute host, and type."""
    return IMPL.console_pool_get_by_host_type(context,
                                              compute_host,
                                              proxy_host,
                                              console_type)


def console_pool_get_all_by_host_type(context, host, console_type):
    """Fetch all pools for given proxy host and type."""
    return IMPL.console_pool_get_all_by_host_type(context,
                                                  host,
                                                  console_type)


def console_create(context, values):
    """Create a console."""
    return IMPL.console_create(context, values)


def console_delete(context, console_id):
    """Delete a console."""
    return IMPL.console_delete(context, console_id)


def console_get_by_pool_instance(context, pool_id, instance_uuid):
    """Get console entry for a given instance and pool."""
    return IMPL.console_get_by_pool_instance(context, pool_id, instance_uuid)


def console_get_all_by_instance(context, instance_uuid, columns_to_join=None):
    """Get consoles for a given instance."""
    return IMPL.console_get_all_by_instance(context, instance_uuid,
                                            columns_to_join)


def console_get(context, console_id, instance_uuid=None):
    """Get a specific console (possibly on a given instance)."""
    return IMPL.console_get(context, console_id, instance_uuid)

##################


def flavor_create(context, values, projects=None):
    """Create a new instance type."""
    return IMPL.flavor_create(context, values, projects=projects)


def flavor_get_all(context, inactive=False, filters=None, sort_key='flavorid',
                   sort_dir='asc', limit=None, marker=None):
    """Get all instance flavors."""
    return IMPL.flavor_get_all(
        context, inactive=inactive, filters=filters, sort_key=sort_key,
        sort_dir=sort_dir, limit=limit, marker=marker)


def flavor_get(context, id):
    """Get instance type by id."""
    return IMPL.flavor_get(context, id)


def flavor_get_by_name(context, name):
    """Get instance type by name."""
    return IMPL.flavor_get_by_name(context, name)


def flavor_get_by_flavor_id(context, id, read_deleted=None):
    """Get instance type by flavor id."""
    return IMPL.flavor_get_by_flavor_id(context, id, read_deleted)


def flavor_destroy(context, name):
    """Delete an instance type."""
    return IMPL.flavor_destroy(context, name)


def flavor_access_get_by_flavor_id(context, flavor_id):
    """Get flavor access by flavor id."""
    return IMPL.flavor_access_get_by_flavor_id(context, flavor_id)


def flavor_access_add(context, flavor_id, project_id):
    """Add flavor access for project."""
    return IMPL.flavor_access_add(context, flavor_id, project_id)


def flavor_access_remove(context, flavor_id, project_id):
    """Remove flavor access for project."""
    return IMPL.flavor_access_remove(context, flavor_id, project_id)


def flavor_extra_specs_get(context, flavor_id):
    """Get all extra specs for an instance type."""
    return IMPL.flavor_extra_specs_get(context, flavor_id)


def flavor_extra_specs_get_item(context, flavor_id, key):
    """Get extra specs by key and flavor_id."""
    return IMPL.flavor_extra_specs_get_item(context, flavor_id, key)


def flavor_extra_specs_delete(context, flavor_id, key):
    """Delete the given extra specs item."""
    IMPL.flavor_extra_specs_delete(context, flavor_id, key)


def flavor_extra_specs_update_or_create(context, flavor_id,
                                               extra_specs):
    """Create or update instance type extra specs.

    This adds or modifies the key/value pairs specified in the
    extra specs dict argument
    """
    IMPL.flavor_extra_specs_update_or_create(context, flavor_id,
                                                    extra_specs)

####################


def pci_device_get_by_addr(context, node_id, dev_addr):
    """Get PCI device by address."""
    return IMPL.pci_device_get_by_addr(context, node_id, dev_addr)


def pci_device_get_by_id(context, id):
    """Get PCI device by id."""
    return IMPL.pci_device_get_by_id(context, id)


def pci_device_get_all_by_node(context, node_id):
    """Get all PCI devices for one host."""
    return IMPL.pci_device_get_all_by_node(context, node_id)


def pci_device_get_all_by_instance_uuid(context, instance_uuid):
    """Get PCI devices allocated to instance."""
    return IMPL.pci_device_get_all_by_instance_uuid(context, instance_uuid)


def pci_device_destroy(context, node_id, address):
    """Delete a PCI device record."""
    return IMPL.pci_device_destroy(context, node_id, address)


def pci_device_update(context, node_id, address, value):
    """Update a pci device."""
    return IMPL.pci_device_update(context, node_id, address, value)


###################

def cell_create(context, values):
    """Create a new child Cell entry."""
    return IMPL.cell_create(context, values)


def cell_update(context, cell_name, values):
    """Update a child Cell entry."""
    return IMPL.cell_update(context, cell_name, values)


def cell_delete(context, cell_name):
    """Delete a child Cell."""
    return IMPL.cell_delete(context, cell_name)


def cell_get(context, cell_name):
    """Get a specific child Cell."""
    return IMPL.cell_get(context, cell_name)


def cell_get_all(context):
    """Get all child Cells."""
    return IMPL.cell_get_all(context)


####################


def instance_metadata_get(context, instance_uuid):
    """Get all metadata for an instance."""
    return IMPL.instance_metadata_get(context, instance_uuid)


def instance_metadata_delete(context, instance_uuid, key):
    """Delete the given metadata item."""
    IMPL.instance_metadata_delete(context, instance_uuid, key)


def instance_metadata_update(context, instance_uuid, metadata, delete):
    """Update metadata if it exists, otherwise create it."""
    return IMPL.instance_metadata_update(context, instance_uuid,
                                         metadata, delete)


####################


def instance_system_metadata_get(context, instance_uuid):
    """Get all system metadata for an instance."""
    return IMPL.instance_system_metadata_get(context, instance_uuid)


def instance_system_metadata_update(context, instance_uuid, metadata, delete):
    """Update metadata if it exists, otherwise create it."""
    IMPL.instance_system_metadata_update(
            context, instance_uuid, metadata, delete)


####################


def agent_build_create(context, values):
    """Create a new agent build entry."""
    return IMPL.agent_build_create(context, values)


def agent_build_get_by_triple(context, hypervisor, os, architecture):
    """Get agent build by hypervisor/OS/architecture triple."""
    return IMPL.agent_build_get_by_triple(context, hypervisor, os,
            architecture)


def agent_build_get_all(context, hypervisor=None):
    """Get all agent builds."""
    return IMPL.agent_build_get_all(context, hypervisor)


def agent_build_destroy(context, agent_update_id):
    """Destroy agent build entry."""
    IMPL.agent_build_destroy(context, agent_update_id)


def agent_build_update(context, agent_build_id, values):
    """Update agent build entry."""
    IMPL.agent_build_update(context, agent_build_id, values)


####################


def bw_usage_get(context, uuid, start_period, mac, use_slave=False):
    """Return bw usage for instance and mac in a given audit period."""
    return IMPL.bw_usage_get(context, uuid, start_period, mac,
                             use_slave=use_slave)


def bw_usage_get_by_uuids(context, uuids, start_period, use_slave=False):
    """Return bw usages for instance(s) in a given audit period."""
    return IMPL.bw_usage_get_by_uuids(context, uuids, start_period,
                                      use_slave=use_slave)


def bw_usage_update(context, uuid, mac, start_period, bw_in, bw_out,
                    last_ctr_in, last_ctr_out, last_refreshed=None,
                    update_cells=True):
    """Update cached bandwidth usage for an instance's network based on mac
    address.  Creates new record if needed.
    """
    rv = IMPL.bw_usage_update(context, uuid, mac, start_period, bw_in,
            bw_out, last_ctr_in, last_ctr_out, last_refreshed=last_refreshed)
    if update_cells:
        try:
            cells_rpcapi.CellsAPI().bw_usage_update_at_top(context,
                    uuid, mac, start_period, bw_in, bw_out,
                    last_ctr_in, last_ctr_out, last_refreshed)
        except Exception:
            LOG.exception(_("Failed to notify cells of bw_usage update"))
    return rv


###################


def vol_get_usage_by_time(context, begin):
    """Return volumes usage that have been updated after a specified time."""
    return IMPL.vol_get_usage_by_time(context, begin)


def vol_usage_update(context, id, rd_req, rd_bytes, wr_req, wr_bytes,
                     instance_id, project_id, user_id, availability_zone,
                     update_totals=False):
    """Update cached volume usage for a volume

       Creates new record if needed.
    """
    return IMPL.vol_usage_update(context, id, rd_req, rd_bytes, wr_req,
                                 wr_bytes, instance_id, project_id, user_id,
                                 availability_zone,
                                 update_totals=update_totals)


###################


def s3_image_get(context, image_id):
    """Find local s3 image represented by the provided id."""
    return IMPL.s3_image_get(context, image_id)


def s3_image_get_by_uuid(context, image_uuid):
    """Find local s3 image represented by the provided uuid."""
    return IMPL.s3_image_get_by_uuid(context, image_uuid)


def s3_image_create(context, image_uuid):
    """Create local s3 image represented by provided uuid."""
    return IMPL.s3_image_create(context, image_uuid)


####################


def aggregate_create(context, values, metadata=None):
    """Create a new aggregate with metadata."""
    return IMPL.aggregate_create(context, values, metadata)


def aggregate_get(context, aggregate_id):
    """Get a specific aggregate by id."""
    return IMPL.aggregate_get(context, aggregate_id)


def aggregate_get_by_host(context, host, key=None):
    """Get a list of aggregates that host belongs to."""
    return IMPL.aggregate_get_by_host(context, host, key)


def aggregate_metadata_get_by_host(context, host, key=None):
    """Get metadata for all aggregates that host belongs to.

    Returns a dictionary where each value is a set, this is to cover the case
    where there two aggregates have different values for the same key.
    Optional key filter
    """
    return IMPL.aggregate_metadata_get_by_host(context, host, key)


def aggregate_metadata_get_by_metadata_key(context, aggregate_id, key):
    """Get metadata for an aggregate by metadata key."""
    return IMPL.aggregate_metadata_get_by_metadata_key(context, aggregate_id,
                                                        key)


def aggregate_host_get_by_metadata_key(context, key):
    """Get hosts with a specific metadata key metadata for all aggregates.

    Returns a dictionary where each key is a hostname and each value is a set
    of the key values
    return value:  {machine: set( az1, az2 )}
    """
    return IMPL.aggregate_host_get_by_metadata_key(context, key)


def aggregate_get_by_metadata_key(context, key):
    return IMPL.aggregate_get_by_metadata_key(context, key)


def aggregate_update(context, aggregate_id, values):
    """Update the attributes of an aggregates.

    If values contains a metadata key, it updates the aggregate metadata too.
    """
    return IMPL.aggregate_update(context, aggregate_id, values)


def aggregate_delete(context, aggregate_id):
    """Delete an aggregate."""
    return IMPL.aggregate_delete(context, aggregate_id)


def aggregate_get_all(context):
    """Get all aggregates."""
    return IMPL.aggregate_get_all(context)


def aggregate_metadata_add(context, aggregate_id, metadata, set_delete=False):
    """Add/update metadata. If set_delete=True, it adds only."""
    IMPL.aggregate_metadata_add(context, aggregate_id, metadata, set_delete)


def aggregate_metadata_get(context, aggregate_id):
    """Get metadata for the specified aggregate."""
    return IMPL.aggregate_metadata_get(context, aggregate_id)


def aggregate_metadata_delete(context, aggregate_id, key):
    """Delete the given metadata key."""
    IMPL.aggregate_metadata_delete(context, aggregate_id, key)


def aggregate_host_add(context, aggregate_id, host):
    """Add host to the aggregate."""
    IMPL.aggregate_host_add(context, aggregate_id, host)


def aggregate_host_get_all(context, aggregate_id):
    """Get hosts for the specified aggregate."""
    return IMPL.aggregate_host_get_all(context, aggregate_id)


def aggregate_host_delete(context, aggregate_id, host):
    """Delete the given host from the aggregate."""
    IMPL.aggregate_host_delete(context, aggregate_id, host)


####################


def instance_fault_create(context, values):
    """Create a new Instance Fault."""
    return IMPL.instance_fault_create(context, values)


def instance_fault_get_by_instance_uuids(context, instance_uuids):
    """Get all instance faults for the provided instance_uuids."""
    return IMPL.instance_fault_get_by_instance_uuids(context, instance_uuids)


####################


def action_start(context, values):
    """Start an action for an instance."""
    return IMPL.action_start(context, values)


def action_finish(context, values):
    """Finish an action for an instance."""
    return IMPL.action_finish(context, values)


def actions_get(context, uuid):
    """Get all instance actions for the provided instance."""
    return IMPL.actions_get(context, uuid)


def action_get_by_request_id(context, uuid, request_id):
    """Get the action by request_id and given instance."""
    return IMPL.action_get_by_request_id(context, uuid, request_id)


def action_event_start(context, values):
    """Start an event on an instance action."""
    return IMPL.action_event_start(context, values)


def action_event_finish(context, values):
    """Finish an event on an instance action."""
    return IMPL.action_event_finish(context, values)


def action_events_get(context, action_id):
    """Get the events by action id."""
    return IMPL.action_events_get(context, action_id)


def action_event_get_by_id(context, action_id, event_id):
    return IMPL.action_event_get_by_id(context, action_id, event_id)


####################


def get_ec2_instance_id_by_uuid(context, instance_id):
    """Get ec2 id through uuid from instance_id_mappings table."""
    return IMPL.get_ec2_instance_id_by_uuid(context, instance_id)


def get_instance_uuid_by_ec2_id(context, ec2_id):
    """Get uuid through ec2 id from instance_id_mappings table."""
    return IMPL.get_instance_uuid_by_ec2_id(context, ec2_id)


def ec2_instance_create(context, instance_uuid, id=None):
    """Create the ec2 id to instance uuid mapping on demand."""
    return IMPL.ec2_instance_create(context, instance_uuid, id)


def ec2_instance_get_by_uuid(context, instance_uuid):
    return IMPL.ec2_instance_get_by_uuid(context, instance_uuid)


def ec2_instance_get_by_id(context, instance_id):
    return IMPL.ec2_instance_get_by_id(context, instance_id)


####################


def task_log_end_task(context, task_name,
                        period_beginning,
                        period_ending,
                        host,
                        errors,
                        message=None):
    """Mark a task as complete for a given host/time period."""
    return IMPL.task_log_end_task(context, task_name,
                                  period_beginning,
                                  period_ending,
                                  host,
                                  errors,
                                  message)


def task_log_begin_task(context, task_name,
                        period_beginning,
                        period_ending,
                        host,
                        task_items=None,
                        message=None):
    """Mark a task as started for a given host/time period."""
    return IMPL.task_log_begin_task(context, task_name,
                                    period_beginning,
                                    period_ending,
                                    host,
                                    task_items,
                                    message)


def task_log_get_all(context, task_name, period_beginning,
                 period_ending, host=None, state=None):
    return IMPL.task_log_get_all(context, task_name, period_beginning,
                 period_ending, host, state)


def task_log_get(context, task_name, period_beginning,
                 period_ending, host, state=None):
    return IMPL.task_log_get(context, task_name, period_beginning,
                 period_ending, host, state)


####################


def archive_deleted_rows(context, max_rows=None):
    """Move up to max_rows rows from production tables to corresponding shadow
    tables.

    :returns: number of rows archived.
    """
    return IMPL.archive_deleted_rows(context, max_rows=max_rows)


def archive_deleted_rows_for_table(context, tablename, max_rows=None):
    """Move up to max_rows rows from tablename to corresponding shadow
    table.

    :returns: number of rows archived.
    """
    return IMPL.archive_deleted_rows_for_table(context, tablename,
                                               max_rows=max_rows)
