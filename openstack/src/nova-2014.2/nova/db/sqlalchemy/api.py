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

"""Implementation of SQLAlchemy backend."""

import collections
import copy
import datetime
import functools
import sys
import threading
import time
import uuid

from oslo.config import cfg
from oslo.db import exception as db_exc
from oslo.db.sqlalchemy import session as db_session
from oslo.db.sqlalchemy import utils as sqlalchemyutils
import six
from sqlalchemy import and_
from sqlalchemy import Boolean
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import or_
from sqlalchemy.orm import contains_eager
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import joinedload_all
from sqlalchemy.orm import noload
from sqlalchemy.schema import Table
from sqlalchemy import sql
from sqlalchemy.sql.expression import asc
from sqlalchemy.sql.expression import desc
from sqlalchemy.sql import false
from sqlalchemy.sql import func
from sqlalchemy.sql import null
from sqlalchemy.sql import true
from sqlalchemy import String

from nova import block_device
from nova.compute import task_states
from nova.compute import vm_states
import nova.context
from nova.db.sqlalchemy import models
from nova import exception
from nova.i18n import _
from nova.openstack.common import excutils
from nova.openstack.common import log as logging
from nova.openstack.common import timeutils
from nova.openstack.common import uuidutils
from nova import quota

db_opts = [
    cfg.StrOpt('osapi_compute_unique_server_name_scope',
               default='',
               help='When set, compute API will consider duplicate hostnames '
                    'invalid within the specified scope, regardless of case. '
                    'Should be empty, "project" or "global".'),
]

CONF = cfg.CONF
CONF.register_opts(db_opts)
CONF.import_opt('compute_topic', 'nova.compute.rpcapi')

LOG = logging.getLogger(__name__)


_ENGINE_FACADE = None
_LOCK = threading.Lock()


def _create_facade_lazily():
    global _LOCK, _ENGINE_FACADE
    if _ENGINE_FACADE is None:
        with _LOCK:
            if _ENGINE_FACADE is None:
                _ENGINE_FACADE = db_session.EngineFacade.from_config(CONF)
    return _ENGINE_FACADE


def get_engine(use_slave=False):
    facade = _create_facade_lazily()
    return facade.get_engine(use_slave=use_slave)


def get_session(use_slave=False, **kwargs):
    facade = _create_facade_lazily()
    return facade.get_session(use_slave=use_slave, **kwargs)


_SHADOW_TABLE_PREFIX = 'shadow_'
_DEFAULT_QUOTA_NAME = 'default'
PER_PROJECT_QUOTAS = ['fixed_ips', 'floating_ips', 'networks']


def get_backend():
    """The backend is this module itself."""
    return sys.modules[__name__]


def require_admin_context(f):
    """Decorator to require admin request context.

    The first argument to the wrapped function must be the context.

    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        nova.context.require_admin_context(args[0])
        return f(*args, **kwargs)
    return wrapper


def require_context(f):
    """Decorator to require *any* user or admin context.

    This does no authorization for user or project access matching, see
    :py:func:`nova.context.authorize_project_context` and
    :py:func:`nova.context.authorize_user_context`.

    The first argument to the wrapped function must be the context.

    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        nova.context.require_context(args[0])
        return f(*args, **kwargs)
    return wrapper


def require_instance_exists_using_uuid(f):
    """Decorator to require the specified instance to exist.

    Requires the wrapped function to use context and instance_uuid as
    their first two arguments.
    """
    @functools.wraps(f)
    def wrapper(context, instance_uuid, *args, **kwargs):
        instance_get_by_uuid(context, instance_uuid)
        return f(context, instance_uuid, *args, **kwargs)

    return wrapper


def require_aggregate_exists(f):
    """Decorator to require the specified aggregate to exist.

    Requires the wrapped function to use context and aggregate_id as
    their first two arguments.
    """

    @functools.wraps(f)
    def wrapper(context, aggregate_id, *args, **kwargs):
        aggregate_get(context, aggregate_id)
        return f(context, aggregate_id, *args, **kwargs)
    return wrapper


def _retry_on_deadlock(f):
    """Decorator to retry a DB API call if Deadlock was received."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        while True:
            try:
                return f(*args, **kwargs)
            except db_exc.DBDeadlock:
                LOG.warn(_("Deadlock detected when running "
                           "'%(func_name)s': Retrying..."),
                           dict(func_name=f.__name__))
                # Retry!
                time.sleep(0.5)
                continue
    functools.update_wrapper(wrapped, f)
    return wrapped


def model_query(context, model, *args, **kwargs):
    """Query helper that accounts for context's `read_deleted` field.

    :param context: context to query under
    :param use_slave: If true, use slave_connection
    :param session: if present, the session to use
    :param read_deleted: if present, overrides context's read_deleted field.
    :param project_only: if present and context is user-type, then restrict
            query to match the context's project_id. If set to 'allow_none',
            restriction includes project_id = None.
    :param base_model: Where model_query is passed a "model" parameter which is
            not a subclass of NovaBase, we should pass an extra base_model
            parameter that is a subclass of NovaBase and corresponds to the
            model parameter.
    """

    use_slave = kwargs.get('use_slave') or False
    if CONF.database.slave_connection == '':
        use_slave = False

    session = kwargs.get('session') or get_session(use_slave=use_slave)
    read_deleted = kwargs.get('read_deleted') or context.read_deleted
    project_only = kwargs.get('project_only', False)

    def issubclassof_nova_base(obj):
        return isinstance(obj, type) and issubclass(obj, models.NovaBase)

    base_model = model
    if not issubclassof_nova_base(base_model):
        base_model = kwargs.get('base_model', None)
        if not issubclassof_nova_base(base_model):
            raise Exception(_("model or base_model parameter should be "
                              "subclass of NovaBase"))

    query = session.query(model, *args)

    default_deleted_value = base_model.__mapper__.c.deleted.default.arg
    if read_deleted == 'no':
        query = query.filter(base_model.deleted == default_deleted_value)
    elif read_deleted == 'yes':
        pass  # omit the filter to include deleted and active
    elif read_deleted == 'only':
        query = query.filter(base_model.deleted != default_deleted_value)
    else:
        raise Exception(_("Unrecognized read_deleted value '%s'")
                            % read_deleted)

    if nova.context.is_user_context(context) and project_only:
        if project_only == 'allow_none':
            query = query.\
                filter(or_(base_model.project_id == context.project_id,
                           base_model.project_id == null()))
        else:
            query = query.filter_by(project_id=context.project_id)

    return query


def exact_filter(query, model, filters, legal_keys):
    """Applies exact match filtering to a query.

    Returns the updated query.  Modifies filters argument to remove
    filters consumed.

    :param query: query to apply filters to
    :param model: model object the query applies to, for IN-style
                  filtering
    :param filters: dictionary of filters; values that are lists,
                    tuples, sets, or frozensets cause an 'IN' test to
                    be performed, while exact matching ('==' operator)
                    is used for other values
    :param legal_keys: list of keys to apply exact filtering to
    """

    filter_dict = {}

    # Walk through all the keys
    for key in legal_keys:
        # Skip ones we're not filtering on
        if key not in filters:
            continue

        # OK, filtering on this key; what value do we search for?
        value = filters.pop(key)

        if key in ('metadata', 'system_metadata'):
            column_attr = getattr(model, key)
            if isinstance(value, list):
                for item in value:
                    for k, v in item.iteritems():
                        query = query.filter(column_attr.any(key=k))
                        query = query.filter(column_attr.any(value=v))

            else:
                for k, v in value.iteritems():
                    query = query.filter(column_attr.any(key=k))
                    query = query.filter(column_attr.any(value=v))
        elif isinstance(value, (list, tuple, set, frozenset)):
            # Looking for values in a list; apply to query directly
            column_attr = getattr(model, key)
            query = query.filter(column_attr.in_(value))
        else:
            # OK, simple exact match; save for later
            filter_dict[key] = value

    # Apply simple exact matches
    if filter_dict:
        query = query.filter_by(**filter_dict)

    return query


def convert_objects_related_datetimes(values, *datetime_keys):
    for key in datetime_keys:
        if key in values and values[key]:
            if isinstance(values[key], six.string_types):
                values[key] = timeutils.parse_strtime(values[key])
            # NOTE(danms): Strip UTC timezones from datetimes, since they're
            # stored that way in the database
            values[key] = values[key].replace(tzinfo=None)
    return values


def _sync_instances(context, project_id, user_id, session):
    return dict(zip(('instances', 'cores', 'ram'),
                    _instance_data_get_for_user(
                context, project_id, user_id, session)))


def _sync_floating_ips(context, project_id, user_id, session):
    return dict(floating_ips=_floating_ip_count_by_project(
                context, project_id, session))


def _sync_fixed_ips(context, project_id, user_id, session):
    return dict(fixed_ips=_fixed_ip_count_by_project(
                context, project_id, session))


def _sync_security_groups(context, project_id, user_id, session):
    return dict(security_groups=_security_group_count_by_project_and_user(
                context, project_id, user_id, session))


def _sync_server_groups(context, project_id, user_id, session):
    return dict(server_groups=_instance_group_count_by_project_and_user(
                context, project_id, user_id, session))

QUOTA_SYNC_FUNCTIONS = {
    '_sync_instances': _sync_instances,
    '_sync_floating_ips': _sync_floating_ips,
    '_sync_fixed_ips': _sync_fixed_ips,
    '_sync_security_groups': _sync_security_groups,
    '_sync_server_groups': _sync_server_groups,
}

###################


def constraint(**conditions):
    return Constraint(conditions)


def equal_any(*values):
    return EqualityCondition(values)


def not_equal(*values):
    return InequalityCondition(values)


class Constraint(object):

    def __init__(self, conditions):
        self.conditions = conditions

    def apply(self, model, query):
        for key, condition in self.conditions.iteritems():
            for clause in condition.clauses(getattr(model, key)):
                query = query.filter(clause)
        return query


class EqualityCondition(object):

    def __init__(self, values):
        self.values = values

    def clauses(self, field):
        # method signature requires us to return an iterable even if for OR
        # operator this will actually be a single clause
        return [or_(*[field == value for value in self.values])]


class InequalityCondition(object):

    def __init__(self, values):
        self.values = values

    def clauses(self, field):
        return [field != value for value in self.values]


###################


@require_admin_context
def service_destroy(context, service_id):
    session = get_session()
    with session.begin():
        count = model_query(context, models.Service, session=session).\
                    filter_by(id=service_id).\
                    soft_delete(synchronize_session=False)

        if count == 0:
            raise exception.ServiceNotFound(service_id=service_id)

        model_query(context, models.ComputeNode, session=session).\
                    filter_by(service_id=service_id).\
                    soft_delete(synchronize_session=False)


def _service_get(context, service_id, with_compute_node=True, session=None,
                 use_slave=False):
    query = model_query(context, models.Service, session=session,
                        use_slave=use_slave).\
                     filter_by(id=service_id)

    if with_compute_node:
        query = query.options(joinedload('compute_node'))

    result = query.first()
    if not result:
        raise exception.ServiceNotFound(service_id=service_id)

    return result


@require_admin_context
def service_get(context, service_id, with_compute_node=False,
                use_slave=False):
    return _service_get(context, service_id,
                        with_compute_node=with_compute_node,
                        use_slave=use_slave)


@require_admin_context
def service_get_all(context, disabled=None):
    query = model_query(context, models.Service)

    if disabled is not None:
        query = query.filter_by(disabled=disabled)

    return query.all()


@require_admin_context
def service_get_all_by_topic(context, topic):
    return model_query(context, models.Service, read_deleted="no").\
                filter_by(disabled=False).\
                filter_by(topic=topic).\
                all()


@require_admin_context
def service_get_by_host_and_topic(context, host, topic):
    return model_query(context, models.Service, read_deleted="no").\
                filter_by(disabled=False).\
                filter_by(host=host).\
                filter_by(topic=topic).\
                first()


@require_admin_context
def service_get_all_by_host(context, host):
    return model_query(context, models.Service, read_deleted="no").\
                filter_by(host=host).\
                all()


@require_admin_context
def service_get_by_compute_host(context, host, use_slave=False):
    result = model_query(context, models.Service, read_deleted="no",
                         use_slave=use_slave).\
                options(joinedload('compute_node')).\
                filter_by(host=host).\
                filter_by(topic=CONF.compute_topic).\
                first()

    if not result:
        raise exception.ComputeHostNotFound(host=host)

    return result


@require_admin_context
def service_get_by_args(context, host, binary):
    result = model_query(context, models.Service).\
                     filter_by(host=host).\
                     filter_by(binary=binary).\
                     first()

    if not result:
        raise exception.HostBinaryNotFound(host=host, binary=binary)

    return result


@require_admin_context
def service_create(context, values):
    service_ref = models.Service()
    service_ref.update(values)
    if not CONF.enable_new_services:
        service_ref.disabled = True
    try:
        service_ref.save()
    except db_exc.DBDuplicateEntry as e:
        if 'binary' in e.columns:
            raise exception.ServiceBinaryExists(host=values.get('host'),
                        binary=values.get('binary'))
        raise exception.ServiceTopicExists(host=values.get('host'),
                        topic=values.get('topic'))
    return service_ref


@require_admin_context
@_retry_on_deadlock
def service_update(context, service_id, values):
    session = get_session()
    with session.begin():
        service_ref = _service_get(context, service_id,
                                   with_compute_node=False, session=session)
        service_ref.update(values)

    return service_ref


###################

def compute_node_get(context, compute_id):
    return _compute_node_get(context, compute_id)


def _compute_node_get(context, compute_id, session=None):
    result = model_query(context, models.ComputeNode, session=session).\
            filter_by(id=compute_id).\
            options(joinedload('service')).\
            first()

    if not result:
        raise exception.ComputeHostNotFound(host=compute_id)

    return result


@require_admin_context
def compute_node_get_by_service_id(context, service_id):
    result = model_query(context, models.ComputeNode, read_deleted='no').\
        filter_by(service_id=service_id).\
        first()

    if not result:
        raise exception.ServiceNotFound(service_id=service_id)

    return result


@require_admin_context
def compute_node_get_all(context, no_date_fields):

    # NOTE(msdubov): Using lower-level 'select' queries and joining the tables
    #                manually here allows to gain 3x speed-up and to have 5x
    #                less network load / memory usage compared to the sqla ORM.

    engine = get_engine()

    # Retrieve ComputeNode, Service
    compute_node = models.ComputeNode.__table__
    service = models.Service.__table__

    with engine.begin() as conn:
        redundant_columns = set(['deleted_at', 'created_at', 'updated_at',
                                 'deleted']) if no_date_fields else set([])

        def filter_columns(table):
            return [c for c in table.c if c.name not in redundant_columns]

        compute_node_query = sql.select(filter_columns(compute_node)).\
                                where(compute_node.c.deleted == 0).\
                                order_by(compute_node.c.service_id)
        compute_node_rows = conn.execute(compute_node_query).fetchall()

        service_query = sql.select(filter_columns(service)).\
                            where((service.c.deleted == 0) &
                                  (service.c.binary == 'nova-compute')).\
                            order_by(service.c.id)
        service_rows = conn.execute(service_query).fetchall()

    # Join ComputeNode & Service manually.
    services = {}
    for proxy in service_rows:
        services[proxy['id']] = dict(proxy.items())

    compute_nodes = []
    for proxy in compute_node_rows:
        node = dict(proxy.items())
        node['service'] = services.get(proxy['service_id'])

        compute_nodes.append(node)

    return compute_nodes


@require_admin_context
def compute_node_search_by_hypervisor(context, hypervisor_match):
    field = models.ComputeNode.hypervisor_hostname
    return model_query(context, models.ComputeNode).\
            options(joinedload('service')).\
            filter(field.like('%%%s%%' % hypervisor_match)).\
            all()


@require_admin_context
def compute_node_create(context, values):
    """Creates a new ComputeNode and populates the capacity fields
    with the most recent data.
    """
    datetime_keys = ('created_at', 'deleted_at', 'updated_at')
    convert_objects_related_datetimes(values, *datetime_keys)

    compute_node_ref = models.ComputeNode()
    compute_node_ref.update(values)
    compute_node_ref.save()

    return compute_node_ref


@require_admin_context
@_retry_on_deadlock
def compute_node_update(context, compute_id, values):
    """Updates the ComputeNode record with the most recent data."""

    session = get_session()
    with session.begin():
        compute_ref = _compute_node_get(context, compute_id, session=session)
        # Always update this, even if there's going to be no other
        # changes in data.  This ensures that we invalidate the
        # scheduler cache of compute node data in case of races.
        values['updated_at'] = timeutils.utcnow()
        datetime_keys = ('created_at', 'deleted_at', 'updated_at')
        convert_objects_related_datetimes(values, *datetime_keys)
        compute_ref.update(values)

    return compute_ref


@require_admin_context
def compute_node_delete(context, compute_id):
    """Delete a ComputeNode record."""
    session = get_session()
    with session.begin():
        result = model_query(context, models.ComputeNode, session=session).\
                 filter_by(id=compute_id).\
                 soft_delete(synchronize_session=False)

        if not result:
            raise exception.ComputeHostNotFound(host=compute_id)


def compute_node_statistics(context):
    """Compute statistics over all compute nodes."""
    result = model_query(context,
                         func.count(models.ComputeNode.id),
                         func.sum(models.ComputeNode.vcpus),
                         func.sum(models.ComputeNode.memory_mb),
                         func.sum(models.ComputeNode.local_gb),
                         func.sum(models.ComputeNode.vcpus_used),
                         func.sum(models.ComputeNode.memory_mb_used),
                         func.sum(models.ComputeNode.local_gb_used),
                         func.sum(models.ComputeNode.free_ram_mb),
                         func.sum(models.ComputeNode.free_disk_gb),
                         func.sum(models.ComputeNode.current_workload),
                         func.sum(models.ComputeNode.running_vms),
                         func.sum(models.ComputeNode.disk_available_least),
                         base_model=models.ComputeNode,
                         read_deleted="no").\
                         filter(models.Service.disabled == false()).\
                         filter(
                            models.Service.id ==
                            models.ComputeNode.service_id).\
                         first()

    # Build a dict of the info--making no assumptions about result
    fields = ('count', 'vcpus', 'memory_mb', 'local_gb', 'vcpus_used',
              'memory_mb_used', 'local_gb_used', 'free_ram_mb', 'free_disk_gb',
              'current_workload', 'running_vms', 'disk_available_least')
    return dict((field, int(result[idx] or 0))
                for idx, field in enumerate(fields))


###################


@require_admin_context
def certificate_create(context, values):
    certificate_ref = models.Certificate()
    for (key, value) in values.iteritems():
        certificate_ref[key] = value
    certificate_ref.save()
    return certificate_ref


@require_admin_context
def certificate_get_all_by_project(context, project_id):
    return model_query(context, models.Certificate, read_deleted="no").\
                   filter_by(project_id=project_id).\
                   all()


@require_admin_context
def certificate_get_all_by_user(context, user_id):
    return model_query(context, models.Certificate, read_deleted="no").\
                   filter_by(user_id=user_id).\
                   all()


@require_admin_context
def certificate_get_all_by_user_and_project(context, user_id, project_id):
    return model_query(context, models.Certificate, read_deleted="no").\
                   filter_by(user_id=user_id).\
                   filter_by(project_id=project_id).\
                   all()


###################


@require_context
def floating_ip_get(context, id):
    try:
        result = model_query(context, models.FloatingIp, project_only=True).\
                     filter_by(id=id).\
                     options(joinedload_all('fixed_ip.instance')).\
                     first()

        if not result:
            raise exception.FloatingIpNotFound(id=id)
    except db_exc.DBError:
        msg = _("Invalid floating ip id %s in request") % id
        LOG.warn(msg)
        raise exception.InvalidID(id=id)
    return result


@require_context
def floating_ip_get_pools(context):
    pools = []
    for result in model_query(context, models.FloatingIp.pool,
                              base_model=models.FloatingIp).distinct():
        pools.append({'name': result[0]})
    return pools


@require_context
def floating_ip_allocate_address(context, project_id, pool,
                                 auto_assigned=False):
    nova.context.authorize_project_context(context, project_id)
    session = get_session()
    with session.begin():
        floating_ip_ref = model_query(context, models.FloatingIp,
                                      session=session, read_deleted="no").\
                                  filter_by(fixed_ip_id=None).\
                                  filter_by(project_id=None).\
                                  filter_by(pool=pool).\
                                  with_lockmode('update').\
                                  first()
        # NOTE(vish): if with_lockmode isn't supported, as in sqlite,
        #             then this has concurrency issues
        if not floating_ip_ref:
            raise exception.NoMoreFloatingIps()
        floating_ip_ref['project_id'] = project_id
        floating_ip_ref['auto_assigned'] = auto_assigned
        session.add(floating_ip_ref)
    return floating_ip_ref['address']


@require_context
def floating_ip_bulk_create(context, ips):
    session = get_session()
    result = []
    with session.begin():
        for ip in ips:
            model = models.FloatingIp()
            model.update(ip)
            result.append(model)
            try:
                # NOTE(boris-42): To get existing address we have to do each
                #                  time session.flush()..
                session.add(model)
                session.flush()
            except db_exc.DBDuplicateEntry:
                raise exception.FloatingIpExists(address=ip['address'])
    return result


def _ip_range_splitter(ips, block_size=256):
    """Yields blocks of IPs no more than block_size elements long."""
    out = []
    count = 0
    for ip in ips:
        out.append(ip['address'])
        count += 1

        if count > block_size - 1:
            yield out
            out = []
            count = 0

    if out:
        yield out


@require_context
def floating_ip_bulk_destroy(context, ips):
    session = get_session()
    with session.begin():
        project_id_to_quota_count = collections.defaultdict(int)
        for ip_block in _ip_range_splitter(ips):
            # Find any floating IPs that were not auto_assigned and
            # thus need quota released.
            query = model_query(context, models.FloatingIp).\
                filter(models.FloatingIp.address.in_(ip_block)).\
                filter_by(auto_assigned=False)
            rows = query.all()
            for row in rows:
                # The count is negative since we release quota by
                # reserving negative quota.
                project_id_to_quota_count[row['project_id']] -= 1
            # Delete the floating IPs.
            model_query(context, models.FloatingIp).\
                filter(models.FloatingIp.address.in_(ip_block)).\
                soft_delete(synchronize_session='fetch')
        # Delete the quotas, if needed.
        for project_id, count in project_id_to_quota_count.iteritems():
            try:
                reservations = quota.QUOTAS.reserve(context,
                                                    project_id=project_id,
                                                    floating_ips=count)
                quota.QUOTAS.commit(context,
                                    reservations,
                                    project_id=project_id)
            except Exception:
                with excutils.save_and_reraise_exception():
                    LOG.exception(_("Failed to update usages bulk "
                                    "deallocating floating IP"))


@require_context
def floating_ip_create(context, values):
    floating_ip_ref = models.FloatingIp()
    floating_ip_ref.update(values)
    try:
        floating_ip_ref.save()
    except db_exc.DBDuplicateEntry:
        raise exception.FloatingIpExists(address=values['address'])
    return floating_ip_ref


def _floating_ip_count_by_project(context, project_id, session=None):
    nova.context.authorize_project_context(context, project_id)
    # TODO(tr3buchet): why leave auto_assigned floating IPs out?
    return model_query(context, models.FloatingIp, read_deleted="no",
                       session=session).\
                   filter_by(project_id=project_id).\
                   filter_by(auto_assigned=False).\
                   count()


@require_context
@_retry_on_deadlock
def floating_ip_fixed_ip_associate(context, floating_address,
                                   fixed_address, host):
    session = get_session()
    with session.begin():
        floating_ip_ref = _floating_ip_get_by_address(context,
                                                      floating_address,
                                                      session=session)
        fixed_ip_ref = model_query(context, models.FixedIp, session=session).\
                         filter_by(address=fixed_address).\
                         options(joinedload('network')).\
                         first()
        if floating_ip_ref.fixed_ip_id == fixed_ip_ref["id"]:
            return None
        floating_ip_ref.fixed_ip_id = fixed_ip_ref["id"]
        floating_ip_ref.host = host

        return fixed_ip_ref


@require_context
@_retry_on_deadlock
def floating_ip_deallocate(context, address):
    session = get_session()
    with session.begin():
        return model_query(context, models.FloatingIp, session=session).\
            filter_by(address=address).\
            filter(models.FloatingIp.project_id != null()).\
            update({'project_id': None,
                    'host': None,
                    'auto_assigned': False},
                   synchronize_session=False)


@require_context
def floating_ip_destroy(context, address):
    model_query(context, models.FloatingIp).\
            filter_by(address=address).\
            delete()


@require_context
def floating_ip_disassociate(context, address):
    session = get_session()
    with session.begin():
        floating_ip_ref = model_query(context,
                                      models.FloatingIp,
                                      session=session).\
                            filter_by(address=address).\
                            first()
        if not floating_ip_ref:
            raise exception.FloatingIpNotFoundForAddress(address=address)

        fixed_ip_ref = model_query(context, models.FixedIp, session=session).\
                            filter_by(id=floating_ip_ref['fixed_ip_id']).\
                            options(joinedload('network')).\
                            first()
        floating_ip_ref.fixed_ip_id = None
        floating_ip_ref.host = None

    return fixed_ip_ref


@require_context
def floating_ip_set_auto_assigned(context, address):
    model_query(context, models.FloatingIp).\
            filter_by(address=address).\
            update({'auto_assigned': True})


def _floating_ip_get_all(context, session=None):
    return model_query(context, models.FloatingIp, read_deleted="no",
                       session=session)


@require_admin_context
def floating_ip_get_all(context):
    floating_ip_refs = _floating_ip_get_all(context).all()
    if not floating_ip_refs:
        raise exception.NoFloatingIpsDefined()
    return floating_ip_refs


@require_admin_context
def floating_ip_get_all_by_host(context, host):
    floating_ip_refs = _floating_ip_get_all(context).\
                            filter_by(host=host).\
                            all()
    if not floating_ip_refs:
        raise exception.FloatingIpNotFoundForHost(host=host)
    return floating_ip_refs


@require_context
def floating_ip_get_all_by_project(context, project_id):
    nova.context.authorize_project_context(context, project_id)
    # TODO(tr3buchet): why do we not want auto_assigned floating IPs here?
    return _floating_ip_get_all(context).\
                         filter_by(project_id=project_id).\
                         filter_by(auto_assigned=False).\
                         options(joinedload_all('fixed_ip.instance')).\
                         all()


@require_context
def floating_ip_get_by_address(context, address):
    return _floating_ip_get_by_address(context, address)


def _floating_ip_get_by_address(context, address, session=None):

    # if address string is empty explicitly set it to None
    if not address:
        address = None
    try:
        result = model_query(context, models.FloatingIp, session=session).\
                    filter_by(address=address).\
                    options(joinedload_all('fixed_ip.instance')).\
                    first()

        if not result:
            raise exception.FloatingIpNotFoundForAddress(address=address)
    except db_exc.DBError:
        msg = _("Invalid floating IP %s in request") % address
        LOG.warn(msg)
        raise exception.InvalidIpAddressError(msg)

    # If the floating IP has a project ID set, check to make sure
    # the non-admin user has access.
    if result.project_id and nova.context.is_user_context(context):
        nova.context.authorize_project_context(context, result.project_id)

    return result


@require_context
def floating_ip_get_by_fixed_address(context, fixed_address):
    return model_query(context, models.FloatingIp).\
                       outerjoin(models.FixedIp,
                                 models.FixedIp.id ==
                                 models.FloatingIp.fixed_ip_id).\
                       filter(models.FixedIp.address == fixed_address).\
                       all()


@require_context
def floating_ip_get_by_fixed_ip_id(context, fixed_ip_id):
    return model_query(context, models.FloatingIp).\
                filter_by(fixed_ip_id=fixed_ip_id).\
                all()


@require_context
def floating_ip_update(context, address, values):
    session = get_session()
    with session.begin():
        float_ip_ref = _floating_ip_get_by_address(context, address, session)
        float_ip_ref.update(values)
        try:
            float_ip_ref.save(session=session)
        except db_exc.DBDuplicateEntry:
            raise exception.FloatingIpExists(address=values['address'])
        return float_ip_ref


def _dnsdomain_get(context, session, fqdomain):
    return model_query(context, models.DNSDomain,
                       session=session, read_deleted="no").\
               filter_by(domain=fqdomain).\
               with_lockmode('update').\
               first()


@require_context
def dnsdomain_get(context, fqdomain):
    session = get_session()
    with session.begin():
        return _dnsdomain_get(context, session, fqdomain)


def _dnsdomain_get_or_create(context, session, fqdomain):
    domain_ref = _dnsdomain_get(context, session, fqdomain)
    if not domain_ref:
        dns_ref = models.DNSDomain()
        dns_ref.update({'domain': fqdomain,
                        'availability_zone': None,
                        'project_id': None})
        return dns_ref

    return domain_ref


@require_admin_context
def dnsdomain_register_for_zone(context, fqdomain, zone):
    session = get_session()
    with session.begin():
        domain_ref = _dnsdomain_get_or_create(context, session, fqdomain)
        domain_ref.scope = 'private'
        domain_ref.availability_zone = zone
        session.add(domain_ref)


@require_admin_context
def dnsdomain_register_for_project(context, fqdomain, project):
    session = get_session()
    with session.begin():
        domain_ref = _dnsdomain_get_or_create(context, session, fqdomain)
        domain_ref.scope = 'public'
        domain_ref.project_id = project
        session.add(domain_ref)


@require_admin_context
def dnsdomain_unregister(context, fqdomain):
    model_query(context, models.DNSDomain).\
                 filter_by(domain=fqdomain).\
                 delete()


@require_context
def dnsdomain_list(context):
    query = model_query(context, models.DNSDomain, read_deleted="no")
    return [row.domain for row in query.all()]


def dnsdomain_get_all(context):
    return model_query(context, models.DNSDomain, read_deleted="no").all()


###################


@require_admin_context
def fixed_ip_associate(context, address, instance_uuid, network_id=None,
                       reserved=False):
    """Keyword arguments:
    reserved -- should be a boolean value(True or False), exact value will be
    used to filter on the fixed ip address
    """
    if not uuidutils.is_uuid_like(instance_uuid):
        raise exception.InvalidUUID(uuid=instance_uuid)

    session = get_session()
    with session.begin():
        network_or_none = or_(models.FixedIp.network_id == network_id,
                              models.FixedIp.network_id == null())
        fixed_ip_ref = model_query(context, models.FixedIp, session=session,
                                   read_deleted="no").\
                               filter(network_or_none).\
                               filter_by(reserved=reserved).\
                               filter_by(address=address).\
                               with_lockmode('update').\
                               first()
        # NOTE(vish): if with_lockmode isn't supported, as in sqlite,
        #             then this has concurrency issues
        if fixed_ip_ref is None:
            raise exception.FixedIpNotFoundForNetwork(address=address,
                                            network_uuid=network_id)
        if fixed_ip_ref.instance_uuid:
            raise exception.FixedIpAlreadyInUse(address=address,
                                                instance_uuid=instance_uuid)

        if not fixed_ip_ref.network_id:
            fixed_ip_ref.network_id = network_id
        fixed_ip_ref.instance_uuid = instance_uuid
        session.add(fixed_ip_ref)
    return fixed_ip_ref


@require_admin_context
def fixed_ip_associate_pool(context, network_id, instance_uuid=None,
                            host=None):
    if instance_uuid and not uuidutils.is_uuid_like(instance_uuid):
        raise exception.InvalidUUID(uuid=instance_uuid)

    session = get_session()
    with session.begin():
        network_or_none = or_(models.FixedIp.network_id == network_id,
                              models.FixedIp.network_id == null())
        fixed_ip_ref = model_query(context, models.FixedIp, session=session,
                                   read_deleted="no").\
                               filter(network_or_none).\
                               filter_by(reserved=False).\
                               filter_by(instance_uuid=None).\
                               filter_by(host=None).\
                               with_lockmode('update').\
                               first()
        # NOTE(vish): if with_lockmode isn't supported, as in sqlite,
        #             then this has concurrency issues
        if not fixed_ip_ref:
            raise exception.NoMoreFixedIps()

        if fixed_ip_ref['network_id'] is None:
            fixed_ip_ref['network'] = network_id

        if instance_uuid:
            fixed_ip_ref['instance_uuid'] = instance_uuid

        if host:
            fixed_ip_ref['host'] = host
        session.add(fixed_ip_ref)
    return fixed_ip_ref


@require_context
def fixed_ip_create(context, values):
    fixed_ip_ref = models.FixedIp()
    fixed_ip_ref.update(values)
    try:
        fixed_ip_ref.save()
    except db_exc.DBDuplicateEntry:
        raise exception.FixedIpExists(address=values['address'])
    return fixed_ip_ref


@require_context
def fixed_ip_bulk_create(context, ips):
    session = get_session()
    with session.begin():
        for ip in ips:
            model = models.FixedIp()
            model.update(ip)
            try:
                # NOTE (vsergeyev): To get existing address we have to do each
                #                   time session.flush().
                #                   See related note at line 697.
                session.add(model)
                session.flush()
            except db_exc.DBDuplicateEntry:
                raise exception.FixedIpExists(address=ip['address'])


@require_context
def fixed_ip_disassociate(context, address):
    session = get_session()
    with session.begin():
        _fixed_ip_get_by_address(context, address, session=session).\
                                 update({'instance_uuid': None,
                                         'virtual_interface_id': None})


@require_admin_context
def fixed_ip_disassociate_all_by_timeout(context, host, time):
    session = get_session()
    # NOTE(vish): only update fixed ips that "belong" to this
    #             host; i.e. the network host or the instance
    #             host matches. Two queries necessary because
    #             join with update doesn't work.
    with session.begin():
        host_filter = or_(and_(models.Instance.host == host,
                               models.Network.multi_host == true()),
                          models.Network.host == host)
        result = model_query(context, models.FixedIp.id,
                             base_model=models.FixedIp, read_deleted="no",
                             session=session).\
                filter(models.FixedIp.allocated == false()).\
                filter(models.FixedIp.updated_at < time).\
                join((models.Network,
                      models.Network.id == models.FixedIp.network_id)).\
                join((models.Instance,
                      models.Instance.uuid == models.FixedIp.instance_uuid)).\
                filter(host_filter).\
                all()
        fixed_ip_ids = [fip[0] for fip in result]
        if not fixed_ip_ids:
            return 0
        result = model_query(context, models.FixedIp, session=session).\
                             filter(models.FixedIp.id.in_(fixed_ip_ids)).\
                             update({'instance_uuid': None,
                                     'leased': False,
                                     'updated_at': timeutils.utcnow()},
                                    synchronize_session='fetch')
        return result


@require_context
def fixed_ip_get(context, id, get_network=False):
    query = model_query(context, models.FixedIp).filter_by(id=id)
    if get_network:
        query = query.options(joinedload('network'))
    result = query.first()
    if not result:
        raise exception.FixedIpNotFound(id=id)

    # FIXME(sirp): shouldn't we just use project_only here to restrict the
    # results?
    if (nova.context.is_user_context(context) and
            result['instance_uuid'] is not None):
        instance = instance_get_by_uuid(context.elevated(read_deleted='yes'),
                                        result['instance_uuid'])
        nova.context.authorize_project_context(context, instance.project_id)

    return result


@require_admin_context
def fixed_ip_get_all(context):
    result = model_query(context, models.FixedIp, read_deleted="yes").all()
    if not result:
        raise exception.NoFixedIpsDefined()

    return result


@require_context
def fixed_ip_get_by_address(context, address, columns_to_join=None):
    return _fixed_ip_get_by_address(context, address,
                                    columns_to_join=columns_to_join)


def _fixed_ip_get_by_address(context, address, session=None,
                             columns_to_join=None):
    if session is None:
        session = get_session()
    if columns_to_join is None:
        columns_to_join = []

    with session.begin(subtransactions=True):
        try:
            result = model_query(context, models.FixedIp, session=session)
            for column in columns_to_join:
                result = result.options(joinedload_all(column))
            result = result.filter_by(address=address).first()
            if not result:
                raise exception.FixedIpNotFoundForAddress(address=address)
        except db_exc.DBError:
            msg = _("Invalid fixed IP Address %s in request") % address
            LOG.warn(msg)
            raise exception.FixedIpInvalid(msg)

        # NOTE(sirp): shouldn't we just use project_only here to restrict the
        # results?
        if (nova.context.is_user_context(context) and
                result['instance_uuid'] is not None):
            instance = _instance_get_by_uuid(
                context.elevated(read_deleted='yes'),
                result['instance_uuid'],
                session
            )
            nova.context.authorize_project_context(context,
                                                   instance.project_id)

    return result


@require_admin_context
def fixed_ip_get_by_address_detailed(context, address):
    """:returns: a tuple of (models.FixedIp, models.Network, models.Instance)
    """
    try:
        result = model_query(context, models.FixedIp,
                             models.Network, models.Instance).\
                             filter_by(address=address).\
                             outerjoin((models.Network,
                                        models.Network.id ==
                                        models.FixedIp.network_id)).\
                             outerjoin((models.Instance,
                                        models.Instance.uuid ==
                                        models.FixedIp.instance_uuid)).\
            first()

        if not result:
            raise exception.FixedIpNotFoundForAddress(address=address)

    except db_exc.DBError:
        msg = _("Invalid fixed IP Address %s in request") % address
        LOG.warn(msg)
        raise exception.FixedIpInvalid(msg)

    return result


@require_context
def fixed_ip_get_by_floating_address(context, floating_address):
    return model_query(context, models.FixedIp).\
                       outerjoin(models.FloatingIp,
                                 models.FloatingIp.fixed_ip_id ==
                                 models.FixedIp.id).\
                       filter(models.FloatingIp.address == floating_address).\
                       first()
    # NOTE(tr3buchet) please don't invent an exception here, empty list is fine


@require_context
def fixed_ip_get_by_instance(context, instance_uuid):
    if not uuidutils.is_uuid_like(instance_uuid):
        raise exception.InvalidUUID(uuid=instance_uuid)

    result = model_query(context, models.FixedIp, read_deleted="no").\
                 filter_by(instance_uuid=instance_uuid).\
                 all()

    if not result:
        raise exception.FixedIpNotFoundForInstance(instance_uuid=instance_uuid)

    return result


@require_admin_context
def fixed_ip_get_by_host(context, host):
    session = get_session()
    with session.begin():
        instance_uuids = _instance_get_all_uuids_by_host(context, host,
                                                         session=session)
        if not instance_uuids:
            return []

        return model_query(context, models.FixedIp, session=session).\
                 filter(models.FixedIp.instance_uuid.in_(instance_uuids)).\
                 all()


@require_context
def fixed_ip_get_by_network_host(context, network_id, host):
    result = model_query(context, models.FixedIp, read_deleted="no").\
                 filter_by(network_id=network_id).\
                 filter_by(host=host).\
                 first()

    if not result:
        raise exception.FixedIpNotFoundForNetworkHost(network_id=network_id,
                                                      host=host)
    return result


@require_context
def fixed_ips_by_virtual_interface(context, vif_id):
    result = model_query(context, models.FixedIp, read_deleted="no").\
                 filter_by(virtual_interface_id=vif_id).\
                 all()

    return result


@require_context
def fixed_ip_update(context, address, values):
    session = get_session()
    with session.begin():
        _fixed_ip_get_by_address(context, address, session=session).\
                                 update(values)


def _fixed_ip_count_by_project(context, project_id, session=None):
    nova.context.authorize_project_context(context, project_id)
    return model_query(context, models.FixedIp.id,
                       base_model=models.FixedIp, read_deleted="no",
                       session=session).\
                join((models.Instance,
                      models.Instance.uuid == models.FixedIp.instance_uuid)).\
                filter(models.Instance.project_id == project_id).\
                count()


###################


@require_context
def virtual_interface_create(context, values):
    """Create a new virtual interface record in the database.

    :param values: = dict containing column values
    """
    try:
        vif_ref = models.VirtualInterface()
        vif_ref.update(values)
        vif_ref.save()
    except db_exc.DBError:
        raise exception.VirtualInterfaceCreateException()

    return vif_ref


def _virtual_interface_query(context, session=None, use_slave=False):
    return model_query(context, models.VirtualInterface, session=session,
                       read_deleted="no", use_slave=use_slave)


@require_context
def virtual_interface_get(context, vif_id):
    """Gets a virtual interface from the table.

    :param vif_id: = id of the virtual interface
    """
    vif_ref = _virtual_interface_query(context).\
                      filter_by(id=vif_id).\
                      first()
    return vif_ref


@require_context
def virtual_interface_get_by_address(context, address):
    """Gets a virtual interface from the table.

    :param address: = the address of the interface you're looking to get
    """
    try:
        vif_ref = _virtual_interface_query(context).\
                          filter_by(address=address).\
                          first()
    except db_exc.DBError:
        msg = _("Invalid virtual interface address %s in request") % address
        LOG.warn(msg)
        raise exception.InvalidIpAddressError(msg)
    return vif_ref


@require_context
def virtual_interface_get_by_uuid(context, vif_uuid):
    """Gets a virtual interface from the table.

    :param vif_uuid: the uuid of the interface you're looking to get
    """
    vif_ref = _virtual_interface_query(context).\
                      filter_by(uuid=vif_uuid).\
                      first()
    return vif_ref


@require_context
@require_instance_exists_using_uuid
def virtual_interface_get_by_instance(context, instance_uuid, use_slave=False):
    """Gets all virtual interfaces for instance.

    :param instance_uuid: = uuid of the instance to retrieve vifs for
    """
    vif_refs = _virtual_interface_query(context, use_slave=use_slave).\
                       filter_by(instance_uuid=instance_uuid).\
                       order_by(asc("created_at"), asc("id")).\
                       all()
    return vif_refs


@require_context
def virtual_interface_get_by_instance_and_network(context, instance_uuid,
                                                  network_id):
    """Gets virtual interface for instance that's associated with network."""
    vif_ref = _virtual_interface_query(context).\
                      filter_by(instance_uuid=instance_uuid).\
                      filter_by(network_id=network_id).\
                      first()
    return vif_ref


@require_context
def virtual_interface_delete_by_instance(context, instance_uuid):
    """Delete virtual interface records that are associated
    with the instance given by instance_id.

    :param instance_uuid: = uuid of instance
    """
    _virtual_interface_query(context).\
           filter_by(instance_uuid=instance_uuid).\
           soft_delete()


@require_context
def virtual_interface_get_all(context):
    """Get all vifs."""
    vif_refs = _virtual_interface_query(context).all()
    return vif_refs


###################


def _metadata_refs(metadata_dict, meta_class):
    metadata_refs = []
    if metadata_dict:
        for k, v in metadata_dict.iteritems():
            metadata_ref = meta_class()
            metadata_ref['key'] = k
            metadata_ref['value'] = v
            metadata_refs.append(metadata_ref)
    return metadata_refs


def _validate_unique_server_name(context, session, name):
    if not CONF.osapi_compute_unique_server_name_scope:
        return

    lowername = name.lower()
    base_query = model_query(context, models.Instance, session=session,
                             read_deleted=False).\
            filter(func.lower(models.Instance.hostname) == lowername)

    if CONF.osapi_compute_unique_server_name_scope == 'project':
        instance_with_same_name = base_query.\
                        filter_by(project_id=context.project_id).\
                        count()

    elif CONF.osapi_compute_unique_server_name_scope == 'global':
        instance_with_same_name = base_query.count()

    else:
        msg = _('Unknown osapi_compute_unique_server_name_scope value: %s'
                ' Flag must be empty, "global" or'
                ' "project"') % CONF.osapi_compute_unique_server_name_scope
        LOG.warn(msg)
        return

    if instance_with_same_name > 0:
        raise exception.InstanceExists(name=lowername)


def _handle_objects_related_type_conversions(values):
    """Make sure that certain things in values (which may have come from
    an objects.instance.Instance object) are in suitable form for the
    database.
    """
    # NOTE(danms): Make sure IP addresses are passed as strings to
    # the database engine
    for key in ('access_ip_v4', 'access_ip_v6'):
        if key in values and values[key] is not None:
            values[key] = str(values[key])

    datetime_keys = ('created_at', 'deleted_at', 'updated_at',
                     'launched_at', 'terminated_at', 'scheduled_at')
    convert_objects_related_datetimes(values, *datetime_keys)


@require_context
def instance_create(context, values):
    """Create a new Instance record in the database.

    context - request context object
    values - dict containing column values.
    """

    # NOTE(rpodolyaka): create the default security group, if it doesn't exist.
    # This must be done in a separate transaction, so that this one is not
    # aborted in case a concurrent one succeeds first and the unique constraint
    # for security group names is violated by a concurrent INSERT
    security_group_ensure_default(context)

    values = values.copy()
    values['metadata'] = _metadata_refs(
            values.get('metadata'), models.InstanceMetadata)

    values['system_metadata'] = _metadata_refs(
            values.get('system_metadata'), models.InstanceSystemMetadata)
    _handle_objects_related_type_conversions(values)

    instance_ref = models.Instance()
    if not values.get('uuid'):
        values['uuid'] = str(uuid.uuid4())
    instance_ref['info_cache'] = models.InstanceInfoCache()
    info_cache = values.pop('info_cache', None)
    if info_cache is not None:
        instance_ref['info_cache'].update(info_cache)
    security_groups = values.pop('security_groups', [])
    instance_ref.update(values)

    def _get_sec_group_models(session, security_groups):
        models = []
        default_group = _security_group_ensure_default(context, session)
        if 'default' in security_groups:
            models.append(default_group)
            # Generate a new list, so we don't modify the original
            security_groups = [x for x in security_groups if x != 'default']
        if security_groups:
            models.extend(_security_group_get_by_names(context,
                    session, context.project_id, security_groups))
        return models

    session = get_session()
    with session.begin():
        if 'hostname' in values:
            _validate_unique_server_name(context, session, values['hostname'])
        instance_ref.security_groups = _get_sec_group_models(session,
                security_groups)
        session.add(instance_ref)

    # create the instance uuid to ec2_id mapping entry for instance
    ec2_instance_create(context, instance_ref['uuid'])

    _instance_extra_create(context, {'instance_uuid': instance_ref['uuid']})

    return instance_ref


def _instance_data_get_for_user(context, project_id, user_id, session=None):
    result = model_query(context,
                         func.count(models.Instance.id),
                         func.sum(models.Instance.vcpus),
                         func.sum(models.Instance.memory_mb),
                         base_model=models.Instance,
                         session=session).\
                     filter_by(project_id=project_id)
    if user_id:
        result = result.filter_by(user_id=user_id).first()
    else:
        result = result.first()
    # NOTE(vish): convert None to 0
    return (result[0] or 0, result[1] or 0, result[2] or 0)


@require_context
@_retry_on_deadlock
def instance_destroy(context, instance_uuid, constraint=None):
    session = get_session()
    with session.begin():
        if uuidutils.is_uuid_like(instance_uuid):
            instance_ref = _instance_get_by_uuid(context, instance_uuid,
                    session=session)
        else:
            raise exception.InvalidUUID(instance_uuid)

        query = model_query(context, models.Instance, session=session).\
                        filter_by(uuid=instance_uuid)
        if constraint is not None:
            query = constraint.apply(models.Instance, query)
        count = query.soft_delete()
        if count == 0:
            raise exception.ConstraintNotMet()
        model_query(context, models.SecurityGroupInstanceAssociation,
                    session=session).\
                filter_by(instance_uuid=instance_uuid).\
                soft_delete()
        model_query(context, models.InstanceInfoCache, session=session).\
                filter_by(instance_uuid=instance_uuid).\
                soft_delete()
        model_query(context, models.InstanceMetadata, session=session).\
                filter_by(instance_uuid=instance_uuid).\
                soft_delete()
        model_query(context, models.InstanceFault, session=session).\
                filter_by(instance_uuid=instance_uuid).\
                soft_delete()
        model_query(context, models.InstanceExtra, session=session).\
                filter_by(instance_uuid=instance_uuid).\
                soft_delete()
    return instance_ref


@require_context
def instance_get_by_uuid(context, uuid, columns_to_join=None, use_slave=False):
    return _instance_get_by_uuid(context, uuid,
            columns_to_join=columns_to_join, use_slave=use_slave)


def _instance_get_by_uuid(context, uuid, session=None,
                          columns_to_join=None, use_slave=False):
    result = _build_instance_get(context, session=session,
                                 columns_to_join=columns_to_join,
                                 use_slave=use_slave).\
                filter_by(uuid=uuid).\
                first()

    if not result:
        raise exception.InstanceNotFound(instance_id=uuid)

    return result


@require_context
def instance_get(context, instance_id, columns_to_join=None):
    try:
        result = _build_instance_get(context, columns_to_join=columns_to_join
                                     ).filter_by(id=instance_id).first()

        if not result:
            raise exception.InstanceNotFound(instance_id=instance_id)

        return result
    except db_exc.DBError:
        # NOTE(sdague): catch all in case the db engine chokes on the
        # id because it's too long of an int to store.
        msg = _("Invalid instance id %s in request") % instance_id
        LOG.warn(msg)
        raise exception.InvalidID(id=instance_id)


def _build_instance_get(context, session=None,
                        columns_to_join=None, use_slave=False):
    query = model_query(context, models.Instance, session=session,
                        project_only=True, use_slave=use_slave).\
            options(joinedload_all('security_groups.rules')).\
            options(joinedload('info_cache'))
    if columns_to_join is None:
        columns_to_join = ['metadata', 'system_metadata']
    for column in columns_to_join:
        if column in ['info_cache', 'security_groups']:
            # Already always joined above
            continue
        query = query.options(joinedload(column))
    # NOTE(alaski) Stop lazy loading of columns not needed.
    for col in ['metadata', 'system_metadata']:
        if col not in columns_to_join:
            query = query.options(noload(col))
    return query


def _instances_fill_metadata(context, instances,
                             manual_joins=None, use_slave=False):
    """Selectively fill instances with manually-joined metadata. Note that
    instance will be converted to a dict.

    :param context: security context
    :param instances: list of instances to fill
    :param manual_joins: list of tables to manually join (can be any
                         combination of 'metadata' and 'system_metadata' or
                         None to take the default of both)
    """
    uuids = [inst['uuid'] for inst in instances]

    if manual_joins is None:
        manual_joins = ['metadata', 'system_metadata']

    meta = collections.defaultdict(list)
    if 'metadata' in manual_joins:
        for row in _instance_metadata_get_multi(context, uuids,
                                                use_slave=use_slave):
            meta[row['instance_uuid']].append(row)

    sys_meta = collections.defaultdict(list)
    if 'system_metadata' in manual_joins:
        for row in _instance_system_metadata_get_multi(context, uuids,
                                                       use_slave=use_slave):
            sys_meta[row['instance_uuid']].append(row)

    pcidevs = collections.defaultdict(list)
    if 'pci_devices' in manual_joins:
        for row in _instance_pcidevs_get_multi(context, uuids):
            pcidevs[row['instance_uuid']].append(row)

    filled_instances = []
    for inst in instances:
        inst = dict(inst.iteritems())
        inst['system_metadata'] = sys_meta[inst['uuid']]
        inst['metadata'] = meta[inst['uuid']]
        if 'pci_devices' in manual_joins:
            inst['pci_devices'] = pcidevs[inst['uuid']]
        filled_instances.append(inst)

    return filled_instances


def _manual_join_columns(columns_to_join):
    manual_joins = []
    for column in ('metadata', 'system_metadata', 'pci_devices'):
        if column in columns_to_join:
            columns_to_join.remove(column)
            manual_joins.append(column)
    return manual_joins, columns_to_join


@require_context
def instance_get_all(context, columns_to_join=None):
    if columns_to_join is None:
        columns_to_join = ['info_cache', 'security_groups']
        manual_joins = ['metadata', 'system_metadata']
    else:
        manual_joins, columns_to_join = _manual_join_columns(columns_to_join)
    query = model_query(context, models.Instance)
    for column in columns_to_join:
        query = query.options(joinedload(column))
    if not context.is_admin:
        # If we're not admin context, add appropriate filter..
        if context.project_id:
            query = query.filter_by(project_id=context.project_id)
        else:
            query = query.filter_by(user_id=context.user_id)
    instances = query.all()
    return _instances_fill_metadata(context, instances, manual_joins)


@require_context
def instance_get_all_by_filters(context, filters, sort_key, sort_dir,
                                limit=None, marker=None, columns_to_join=None,
                                use_slave=False):
    """Return instances that match all filters.  Deleted instances
    will be returned by default, unless there's a filter that says
    otherwise.

    Depending on the name of a filter, matching for that filter is
    performed using either exact matching or as regular expression
    matching. Exact matching is applied for the following filters::

    |   ['project_id', 'user_id', 'image_ref',
    |    'vm_state', 'instance_type_id', 'uuid',
    |    'metadata', 'host', 'system_metadata']


    A third type of filter (also using exact matching), filters
    based on instance metadata tags when supplied under a special
    key named 'filter'::

    |   filters = {
    |       'filter': [
    |           {'name': 'tag-key', 'value': '<metakey>'},
    |           {'name': 'tag-value', 'value': '<metaval>'},
    |           {'name': 'tag:<metakey>', 'value': '<metaval>'}
    |       ]
    |   }

    Special keys are used to tweek the query further::

    |   'changes-since' - only return instances updated after
    |   'deleted' - only return (or exclude) deleted instances
    |   'soft_deleted' - modify behavior of 'deleted' to either
    |                    include or exclude instances whose
    |                    vm_state is SOFT_DELETED.

    """
    # NOTE(mriedem): If the limit is 0 there is no point in even going
    # to the database since nothing is going to be returned anyway.
    if limit == 0:
        return []

    sort_fn = {'desc': desc, 'asc': asc}

    if CONF.database.slave_connection == '':
        use_slave = False

    session = get_session(use_slave=use_slave)

    if columns_to_join is None:
        columns_to_join = ['info_cache', 'security_groups']
        manual_joins = ['metadata', 'system_metadata']
    else:
        manual_joins, columns_to_join = _manual_join_columns(columns_to_join)

    query_prefix = session.query(models.Instance)
    for column in columns_to_join:
        query_prefix = query_prefix.options(joinedload(column))

    query_prefix = query_prefix.order_by(sort_fn[sort_dir](
            getattr(models.Instance, sort_key)))

    # Make a copy of the filters dictionary to use going forward, as we'll
    # be modifying it and we shouldn't affect the caller's use of it.
    filters = filters.copy()

    if 'changes-since' in filters:
        changes_since = timeutils.normalize_time(filters['changes-since'])
        query_prefix = query_prefix.\
                            filter(models.Instance.updated_at >= changes_since)

    if 'deleted' in filters:
        # Instances can be soft or hard deleted and the query needs to
        # include or exclude both
        if filters.pop('deleted'):
            if filters.pop('soft_deleted', True):
                deleted = or_(
                    models.Instance.deleted == models.Instance.id,
                    models.Instance.vm_state == vm_states.SOFT_DELETED
                    )
                query_prefix = query_prefix.\
                    filter(deleted)
            else:
                query_prefix = query_prefix.\
                    filter(models.Instance.deleted == models.Instance.id)
        else:
            query_prefix = query_prefix.\
                    filter_by(deleted=0)
            if not filters.pop('soft_deleted', False):
                # It would be better to have vm_state not be nullable
                # but until then we test it explicitly as a workaround.
                not_soft_deleted = or_(
                    models.Instance.vm_state != vm_states.SOFT_DELETED,
                    models.Instance.vm_state == null()
                    )
                query_prefix = query_prefix.filter(not_soft_deleted)

    if 'cleaned' in filters:
        if filters.pop('cleaned'):
            query_prefix = query_prefix.filter(models.Instance.cleaned == 1)
        else:
            query_prefix = query_prefix.filter(models.Instance.cleaned == 0)

    if not context.is_admin:
        # If we're not admin context, add appropriate filter..
        if context.project_id:
            filters['project_id'] = context.project_id
        else:
            filters['user_id'] = context.user_id

    # Filters for exact matches that we can do along with the SQL query...
    # For other filters that don't match this, we will do regexp matching
    exact_match_filter_names = ['project_id', 'user_id', 'image_ref',
                                'vm_state', 'instance_type_id', 'uuid',
                                'metadata', 'host', 'task_state',
                                'system_metadata']

    # Filter the query
    query_prefix = exact_filter(query_prefix, models.Instance,
                                filters, exact_match_filter_names)

    query_prefix = regex_filter(query_prefix, models.Instance, filters)
    query_prefix = tag_filter(context, query_prefix, models.Instance,
                              models.InstanceMetadata,
                              models.InstanceMetadata.instance_uuid,
                              filters)

    # paginate query
    if marker is not None:
        try:
            marker = _instance_get_by_uuid(context, marker, session=session)
        except exception.InstanceNotFound:
            raise exception.MarkerNotFound(marker)
    query_prefix = sqlalchemyutils.paginate_query(query_prefix,
                           models.Instance, limit,
                           [sort_key, 'created_at', 'id'],
                           marker=marker,
                           sort_dir=sort_dir)

    return _instances_fill_metadata(context, query_prefix.all(), manual_joins)


def tag_filter(context, query, model, model_metadata,
               model_uuid, filters):
    """Applies tag filtering to a query.

    Returns the updated query.  This method alters filters to remove
    keys that are tags.  This filters on resources by tags - this
    method assumes that the caller will take care of access control

    :param query: query to apply filters to
    :param model: model object the query applies to
    :param filters: dictionary of filters
    """
    if filters.get('filter') is None:
        return query

    or_query = None

    def _to_list(val):
        if isinstance(val, dict):
            val = val.values()
        if not isinstance(val, (tuple, list, set)):
            val = (val,)
        return val

    for filter_block in filters['filter']:
        if not isinstance(filter_block, dict):
            continue

        filter_name = filter_block.get('name')
        if filter_name is None:
            continue

        tag_name = filter_name[4:]
        tag_val = _to_list(filter_block.get('value'))

        if filter_name.startswith('tag-'):
            if tag_name not in ['key', 'value']:
                msg = _("Invalid field name: %s") % tag_name
                raise exception.InvalidParameterValue(err=msg)
            subq = getattr(model_metadata, tag_name).in_(tag_val)
            or_query = subq if or_query is None else or_(or_query, subq)

        elif filter_name.startswith('tag:'):
            subq = model_query(context, model_uuid,
                session=query.session, base_model=model_metadata).\
                filter_by(key=tag_name).\
                filter(model_metadata.value.in_(tag_val))
            query = query.filter(model.uuid.in_(subq))

    if or_query is not None:
        subq = model_query(context, model_uuid,
                session=query.session, base_model=model_metadata).\
                filter(or_query)
        query = query.filter(model.uuid.in_(subq))

    return query


def regex_filter(query, model, filters):
    """Applies regular expression filtering to a query.

    Returns the updated query.

    :param query: query to apply filters to
    :param model: model object the query applies to
    :param filters: dictionary of filters with regex values
    """

    regexp_op_map = {
        'postgresql': '~',
        'mysql': 'REGEXP',
        'sqlite': 'REGEXP'
    }
    db_string = CONF.database.connection.split(':')[0].split('+')[0]
    db_regexp_op = regexp_op_map.get(db_string, 'LIKE')
    for filter_name in filters.iterkeys():
        try:
            column_attr = getattr(model, filter_name)
        except AttributeError:
            continue
        if 'property' == type(column_attr).__name__:
            continue
        if db_regexp_op == 'LIKE':
            query = query.filter(column_attr.op(db_regexp_op)(
                                 '%' + str(filters[filter_name]) + '%'))
        else:
            query = query.filter(column_attr.op(db_regexp_op)(
                                 str(filters[filter_name])))
    return query


def process_sort_params(sort_keys, sort_dirs,
                        default_keys=['created_at', 'id'],
                        default_dir='asc'):
    """Process the sort parameters to include default keys.

    Creates a list of sort keys and a list of sort directions. Adds the default
    keys to the end of the list if they are not already included.

    When adding the default keys to the sort keys list, the associated
    direction is:
    1) The first element in the 'sort_dirs' list (if specified), else
    2) 'default_dir' value (Note that 'asc' is the default value since this is
    the default in sqlalchemy.utils.paginate_query)

    :param sort_keys: List of sort keys to include in the processed list
    :param sort_dirs: List of sort directions to include in the processed list
    :param default_keys: List of sort keys that need to be included in the
                         processed list, they are added at the end of the list
                         if not already specified.
    :param default_dir: Sort direction associated with each of the default
                        keys that are not supplied, used when they are added
                        to the processed list
    :returns: list of sort keys, list of sort directions
    :raise exception.InvalidInput: If more sort directions than sort keys
                                   are specified
    """
    # Determine direction to use for when adding default keys
    if sort_dirs and len(sort_dirs) != 0:
        default_dir_value = sort_dirs[0]
    else:
        default_dir_value = default_dir

    # Create list of keys (do not modify the input list)
    if sort_keys:
        result_keys = list(sort_keys)
    else:
        result_keys = []

    # If a list of directions is not provided, use the default sort direction
    # for all provided keys
    if sort_dirs:
        result_dirs = list(sort_dirs)
    else:
        result_dirs = [default_dir_value for _sort_key in result_keys]

    # Ensure that the key and direction length match
    while len(result_dirs) < len(result_keys):
        result_dirs.append(default_dir_value)
    # Unless more direction are specified, which is an error
    if len(result_dirs) > len(result_keys):
        msg = _("Sort direction size exceeds sort key size")
        raise exception.InvalidInput(reason=msg)

    # Ensure defaults are included
    for key in default_keys:
        if key not in result_keys:
            result_keys.append(key)
            result_dirs.append(default_dir_value)

    return result_keys, result_dirs


@require_context
def instance_get_active_by_window_joined(context, begin, end=None,
                                         project_id=None, host=None,
                                         use_slave=False):
    """Return instances and joins that were active during window."""
    session = get_session(use_slave=use_slave)
    query = session.query(models.Instance)

    query = query.options(joinedload('info_cache')).\
                  options(joinedload('security_groups')).\
                  filter(or_(models.Instance.terminated_at == null(),
                             models.Instance.terminated_at > begin))
    if end:
        query = query.filter(models.Instance.launched_at < end)
    if project_id:
        query = query.filter_by(project_id=project_id)
    if host:
        query = query.filter_by(host=host)

    return _instances_fill_metadata(context, query.all())


def _instance_get_all_query(context, project_only=False,
                            joins=None, use_slave=False):
    if joins is None:
        joins = ['info_cache', 'security_groups']

    query = model_query(context,
                        models.Instance,
                        project_only=project_only,
                        use_slave=use_slave)
    for join in joins:
        query = query.options(joinedload(join))
    return query


@require_admin_context
def instance_get_all_by_host(context, host,
                             columns_to_join=None,
                             use_slave=False):
    return _instances_fill_metadata(context,
      _instance_get_all_query(context,
                              use_slave=use_slave).filter_by(host=host).all(),
                              manual_joins=columns_to_join,
                              use_slave=use_slave)


def _instance_get_all_uuids_by_host(context, host, session=None):
    """Return a list of the instance uuids on a given host.

    Returns a list of UUIDs, not Instance model objects. This internal version
    allows you to specify a session object as a kwarg.
    """
    uuids = []
    for tuple in model_query(context, models.Instance.uuid, read_deleted="no",
                             base_model=models.Instance, session=session).\
                filter_by(host=host).\
                all():
        uuids.append(tuple[0])
    return uuids


@require_admin_context
def instance_get_all_by_host_and_node(context, host, node):
    return _instances_fill_metadata(context,
        _instance_get_all_query(context, joins=[]).filter_by(host=host).
            filter_by(node=node).all(), manual_joins=[])


@require_admin_context
def instance_get_all_by_host_and_not_type(context, host, type_id=None):
    return _instances_fill_metadata(context,
        _instance_get_all_query(context).filter_by(host=host).
                   filter(models.Instance.instance_type_id != type_id).all())


# NOTE(jkoelker) This is only being left here for compat with floating
#                ips. Currently the network_api doesn't return floaters
#                in network_info. Once it starts return the model. This
#                function and its call in compute/manager.py on 1829 can
#                go away
@require_context
def instance_get_floating_address(context, instance_id):
    instance = instance_get(context, instance_id)
    fixed_ips = fixed_ip_get_by_instance(context, instance['uuid'])

    if not fixed_ips:
        return None

    # NOTE(tr3buchet): this only gets the first fixed_ip
    # won't find floating ips associated with other fixed_ips
    floating_ips = floating_ip_get_by_fixed_address(context,
                                                    fixed_ips[0]['address'])
    if not floating_ips:
        return None
    # NOTE(vish): this just returns the first floating ip
    return floating_ips[0]['address']


@require_context
def instance_floating_address_get_all(context, instance_uuid):
    if not uuidutils.is_uuid_like(instance_uuid):
        raise exception.InvalidUUID(uuid=instance_uuid)

    floating_ips = model_query(context,
                               models.FloatingIp.address,
                               base_model=models.FloatingIp).\
        join(models.FloatingIp.fixed_ip).\
        filter_by(instance_uuid=instance_uuid)

    return [floating_ip.address for floating_ip in floating_ips]


# NOTE(hanlind): This method can be removed as conductor RPC API moves to v2.0.
@require_admin_context
def instance_get_all_hung_in_rebooting(context, reboot_window):
    reboot_window = (timeutils.utcnow() -
                     datetime.timedelta(seconds=reboot_window))

    # NOTE(danms): this is only used in the _poll_rebooting_instances()
    # call in compute/manager, so we can avoid the metadata lookups
    # explicitly
    return _instances_fill_metadata(context,
        model_query(context, models.Instance).
            filter(models.Instance.updated_at <= reboot_window).
            filter_by(task_state=task_states.REBOOTING).all(),
        manual_joins=[])


@require_context
def instance_update(context, instance_uuid, values):
    instance_ref = _instance_update(context, instance_uuid, values)[1]
    return instance_ref


@require_context
def instance_update_and_get_original(context, instance_uuid, values,
                                     columns_to_join=None):
    """Set the given properties on an instance and update it. Return
    a shallow copy of the original instance reference, as well as the
    updated one.

    :param context: = request context object
    :param instance_uuid: = instance uuid
    :param values: = dict containing column values

    If "expected_task_state" exists in values, the update can only happen
    when the task state before update matches expected_task_state. Otherwise
    a UnexpectedTaskStateError is thrown.

    :returns: a tuple of the form (old_instance_ref, new_instance_ref)

    Raises NotFound if instance does not exist.
    """
    return _instance_update(context, instance_uuid, values,
                            copy_old_instance=True,
                            columns_to_join=columns_to_join)


# NOTE(danms): This updates the instance's metadata list in-place and in
# the database to avoid stale data and refresh issues. It assumes the
# delete=True behavior of instance_metadata_update(...)
def _instance_metadata_update_in_place(context, instance, metadata_type, model,
                                       metadata, session):
    metadata = dict(metadata)
    to_delete = []
    for keyvalue in instance[metadata_type]:
        key = keyvalue['key']
        if key in metadata:
            keyvalue['value'] = metadata.pop(key)
        elif key not in metadata:
            to_delete.append(keyvalue)

    for condemned in to_delete:
        condemned.soft_delete(session=session)

    for key, value in metadata.iteritems():
        newitem = model()
        newitem.update({'key': key, 'value': value,
                        'instance_uuid': instance['uuid']})
        session.add(newitem)
        instance[metadata_type].append(newitem)


@_retry_on_deadlock
def _instance_update(context, instance_uuid, values, copy_old_instance=False,
                     columns_to_join=None):
    session = get_session()

    if not uuidutils.is_uuid_like(instance_uuid):
        raise exception.InvalidUUID(instance_uuid)

    with session.begin():
        instance_ref = _instance_get_by_uuid(context, instance_uuid,
                                             session=session,
                                             columns_to_join=columns_to_join)
        if "expected_task_state" in values:
            # it is not a db column so always pop out
            expected = values.pop("expected_task_state")
            if not isinstance(expected, (tuple, list, set)):
                expected = (expected,)
            actual_state = instance_ref["task_state"]
            if actual_state not in expected:
                if actual_state == task_states.DELETING:
                    raise exception.UnexpectedDeletingTaskStateError(
                            actual=actual_state, expected=expected)
                else:
                    raise exception.UnexpectedTaskStateError(
                            actual=actual_state, expected=expected)
        if "expected_vm_state" in values:
            expected = values.pop("expected_vm_state")
            if not isinstance(expected, (tuple, list, set)):
                expected = (expected,)
            actual_state = instance_ref["vm_state"]
            if actual_state not in expected:
                raise exception.UnexpectedVMStateError(actual=actual_state,
                                                       expected=expected)

        instance_hostname = instance_ref['hostname'] or ''
        if ("hostname" in values and
                values["hostname"].lower() != instance_hostname.lower()):
                _validate_unique_server_name(context,
                                             session,
                                             values['hostname'])

        if copy_old_instance:
            old_instance_ref = copy.copy(instance_ref)
        else:
            old_instance_ref = None

        metadata = values.get('metadata')
        if metadata is not None:
            _instance_metadata_update_in_place(context, instance_ref,
                                               'metadata',
                                               models.InstanceMetadata,
                                               values.pop('metadata'),
                                               session)

        system_metadata = values.get('system_metadata')
        if system_metadata is not None:
            _instance_metadata_update_in_place(context, instance_ref,
                                               'system_metadata',
                                               models.InstanceSystemMetadata,
                                               values.pop('system_metadata'),
                                               session)

        _handle_objects_related_type_conversions(values)
        instance_ref.update(values)
        session.add(instance_ref)

    return (old_instance_ref, instance_ref)


def instance_add_security_group(context, instance_uuid, security_group_id):
    """Associate the given security group with the given instance."""
    sec_group_ref = models.SecurityGroupInstanceAssociation()
    sec_group_ref.update({'instance_uuid': instance_uuid,
                          'security_group_id': security_group_id})
    sec_group_ref.save()


@require_context
def instance_remove_security_group(context, instance_uuid, security_group_id):
    """Disassociate the given security group from the given instance."""
    model_query(context, models.SecurityGroupInstanceAssociation).\
                filter_by(instance_uuid=instance_uuid).\
                filter_by(security_group_id=security_group_id).\
                soft_delete()


###################


@require_context
def instance_info_cache_get(context, instance_uuid):
    """Gets an instance info cache from the table.

    :param instance_uuid: = uuid of the info cache's instance
    :param session: = optional session object
    """
    return model_query(context, models.InstanceInfoCache).\
                         filter_by(instance_uuid=instance_uuid).\
                         first()


@require_context
def instance_info_cache_update(context, instance_uuid, values):
    """Update an instance info cache record in the table.

    :param instance_uuid: = uuid of info cache's instance
    :param values: = dict containing column values to update
    :param session: = optional session object
    """
    session = get_session()
    with session.begin():
        info_cache = model_query(context, models.InstanceInfoCache,
                                 session=session).\
                         filter_by(instance_uuid=instance_uuid).\
                         first()
        if info_cache and info_cache['deleted']:
            raise exception.InstanceInfoCacheNotFound(
                    instance_uuid=instance_uuid)
        elif not info_cache:
            # NOTE(tr3buchet): just in case someone blows away an instance's
            #                  cache entry, re-create it.
            info_cache = models.InstanceInfoCache()
            values['instance_uuid'] = instance_uuid

        try:
            info_cache.update(values)
        except db_exc.DBDuplicateEntry:
            # NOTE(sirp): Possible race if two greenthreads attempt to
            # recreate the instance cache entry at the same time. First one
            # wins.
            pass

    return info_cache


@require_context
def instance_info_cache_delete(context, instance_uuid):
    """Deletes an existing instance_info_cache record

    :param instance_uuid: = uuid of the instance tied to the cache record
    :param session: = optional session object
    """
    model_query(context, models.InstanceInfoCache).\
                         filter_by(instance_uuid=instance_uuid).\
                         soft_delete()


###################


def _instance_extra_create(context, values):
    inst_extra_ref = models.InstanceExtra()
    inst_extra_ref.update(values)
    inst_extra_ref.save()
    return inst_extra_ref


def instance_extra_update_by_uuid(context, instance_uuid, values):
    return model_query(context, models.InstanceExtra).\
        filter_by(instance_uuid=instance_uuid).\
        update(values)


def _instance_extra_get_by_instance_uuid_query(context, instance_uuid):
    return (model_query(context, models.InstanceExtra)
                         .filter_by(instance_uuid=instance_uuid))


def instance_extra_get_by_instance_uuid(context, instance_uuid):
    query = _instance_extra_get_by_instance_uuid_query(
        context, instance_uuid)
    instance_extra = query.first()
    return instance_extra


###################


@require_context
def key_pair_create(context, values):
    try:
        key_pair_ref = models.KeyPair()
        key_pair_ref.update(values)
        key_pair_ref.save()
        return key_pair_ref
    except db_exc.DBDuplicateEntry:
        raise exception.KeyPairExists(key_name=values['name'])


@require_context
def key_pair_destroy(context, user_id, name):
    nova.context.authorize_user_context(context, user_id)
    result = model_query(context, models.KeyPair).\
                         filter_by(user_id=user_id).\
                         filter_by(name=name).\
                         soft_delete()
    if not result:
        raise exception.KeypairNotFound(user_id=user_id, name=name)


@require_context
def key_pair_get(context, user_id, name):
    nova.context.authorize_user_context(context, user_id)
    result = model_query(context, models.KeyPair).\
                     filter_by(user_id=user_id).\
                     filter_by(name=name).\
                     first()

    if not result:
        raise exception.KeypairNotFound(user_id=user_id, name=name)

    return result


@require_context
def key_pair_get_all_by_user(context, user_id):
    nova.context.authorize_user_context(context, user_id)
    return model_query(context, models.KeyPair, read_deleted="no").\
                   filter_by(user_id=user_id).\
                   all()


def key_pair_count_by_user(context, user_id):
    nova.context.authorize_user_context(context, user_id)
    return model_query(context, models.KeyPair, read_deleted="no").\
                   filter_by(user_id=user_id).\
                   count()


###################


@require_admin_context
def network_associate(context, project_id, network_id=None, force=False):
    """Associate a project with a network.

    called by project_get_networks under certain conditions
    and network manager add_network_to_project()

    only associate if the project doesn't already have a network
    or if force is True

    force solves race condition where a fresh project has multiple instance
    builds simultaneously picked up by multiple network hosts which attempt
    to associate the project with multiple networks
    force should only be used as a direct consequence of user request
    all automated requests should not use force
    """
    session = get_session()
    with session.begin():

        def network_query(project_filter, id=None):
            filter_kwargs = {'project_id': project_filter}
            if id is not None:
                filter_kwargs['id'] = id
            return model_query(context, models.Network, session=session,
                              read_deleted="no").\
                           filter_by(**filter_kwargs).\
                           with_lockmode('update').\
                           first()

        if not force:
            # find out if project has a network
            network_ref = network_query(project_id)

        if force or not network_ref:
            # in force mode or project doesn't have a network so associate
            # with a new network

            # get new network
            network_ref = network_query(None, network_id)
            if not network_ref:
                raise exception.NoMoreNetworks()

            # associate with network
            # NOTE(vish): if with_lockmode isn't supported, as in sqlite,
            #             then this has concurrency issues
            network_ref['project_id'] = project_id
            session.add(network_ref)
    return network_ref


def _network_ips_query(context, network_id):
    return model_query(context, models.FixedIp, read_deleted="no").\
                   filter_by(network_id=network_id)


@require_admin_context
def network_count_reserved_ips(context, network_id):
    return _network_ips_query(context, network_id).\
                    filter_by(reserved=True).\
                    count()


@require_admin_context
def network_create_safe(context, values):
    network_ref = models.Network()
    network_ref['uuid'] = str(uuid.uuid4())
    network_ref.update(values)

    try:
        network_ref.save()
        return network_ref
    except db_exc.DBDuplicateEntry:
        raise exception.DuplicateVlan(vlan=values['vlan'])


@require_admin_context
def network_delete_safe(context, network_id):
    session = get_session()
    with session.begin():
        result = model_query(context, models.FixedIp, session=session,
                             read_deleted="no").\
                         filter_by(network_id=network_id).\
                         filter_by(allocated=True).\
                         count()
        if result != 0:
            raise exception.NetworkInUse(network_id=network_id)
        network_ref = _network_get(context, network_id=network_id,
                                  session=session)

        model_query(context, models.FixedIp, session=session,
                    read_deleted="no").\
                filter_by(network_id=network_id).\
                soft_delete()

        session.delete(network_ref)


@require_admin_context
def network_disassociate(context, network_id, disassociate_host,
                         disassociate_project):
    net_update = {}
    if disassociate_project:
        net_update['project_id'] = None
    if disassociate_host:
        net_update['host'] = None
    network_update(context, network_id, net_update)


def _network_get(context, network_id, session=None, project_only='allow_none'):
    result = model_query(context, models.Network, session=session,
                         project_only=project_only).\
                    filter_by(id=network_id).\
                    first()

    if not result:
        raise exception.NetworkNotFound(network_id=network_id)

    return result


@require_context
def network_get(context, network_id, project_only='allow_none'):
    return _network_get(context, network_id, project_only=project_only)


@require_context
def network_get_all(context, project_only):
    result = model_query(context, models.Network, read_deleted="no",
                         project_only=project_only).all()

    if not result:
        raise exception.NoNetworksFound()

    return result


@require_context
def network_get_all_by_uuids(context, network_uuids, project_only):
    result = model_query(context, models.Network, read_deleted="no",
                         project_only=project_only).\
                filter(models.Network.uuid.in_(network_uuids)).\
                all()

    if not result:
        raise exception.NoNetworksFound()

    # check if the result contains all the networks
    # we are looking for
    for network_uuid in network_uuids:
        for network in result:
            if network['uuid'] == network_uuid:
                break
        else:
            if project_only:
                raise exception.NetworkNotFoundForProject(
                      network_uuid=network_uuid, project_id=context.project_id)
            raise exception.NetworkNotFound(network_id=network_uuid)

    return result

# NOTE(vish): pylint complains because of the long method name, but
#             it fits with the names of the rest of the methods
# pylint: disable=C0103


@require_admin_context
def network_get_associated_fixed_ips(context, network_id, host=None):
    # FIXME(sirp): since this returns fixed_ips, this would be better named
    # fixed_ip_get_all_by_network.
    # NOTE(vish): The ugly joins here are to solve a performance issue and
    #             should be removed once we can add and remove leases
    #             without regenerating the whole list
    vif_and = and_(models.VirtualInterface.id ==
                   models.FixedIp.virtual_interface_id,
                   models.VirtualInterface.deleted == 0)
    inst_and = and_(models.Instance.uuid == models.FixedIp.instance_uuid,
                    models.Instance.deleted == 0)
    session = get_session()
    # NOTE(vish): This subquery left joins the minimum interface id for each
    #             instance. If the join succeeds (i.e. the 11th column is not
    #             null), then the fixed ip is on the first interface.
    subq = session.query(func.min(models.VirtualInterface.id).label("id"),
                         models.VirtualInterface.instance_uuid).\
            group_by(models.VirtualInterface.instance_uuid).subquery()
    subq_and = and_(subq.c.id == models.FixedIp.virtual_interface_id,
            subq.c.instance_uuid == models.VirtualInterface.instance_uuid)
    query = session.query(models.FixedIp.address,
                          models.FixedIp.instance_uuid,
                          models.FixedIp.network_id,
                          models.FixedIp.virtual_interface_id,
                          models.VirtualInterface.address,
                          models.Instance.hostname,
                          models.Instance.updated_at,
                          models.Instance.created_at,
                          models.FixedIp.allocated,
                          models.FixedIp.leased,
                          subq.c.id).\
                          filter(models.FixedIp.deleted == 0).\
                          filter(models.FixedIp.network_id == network_id).\
                          join((models.VirtualInterface, vif_and)).\
                          join((models.Instance, inst_and)).\
                          outerjoin((subq, subq_and)).\
                          filter(models.FixedIp.instance_uuid != null()).\
                          filter(models.FixedIp.virtual_interface_id != null())
    if host:
        query = query.filter(models.Instance.host == host)
    result = query.all()
    data = []
    for datum in result:
        cleaned = {}
        cleaned['address'] = datum[0]
        cleaned['instance_uuid'] = datum[1]
        cleaned['network_id'] = datum[2]
        cleaned['vif_id'] = datum[3]
        cleaned['vif_address'] = datum[4]
        cleaned['instance_hostname'] = datum[5]
        cleaned['instance_updated'] = datum[6]
        cleaned['instance_created'] = datum[7]
        cleaned['allocated'] = datum[8]
        cleaned['leased'] = datum[9]
        # NOTE(vish): default_route is True if this fixed ip is on the first
        #             interface its instance.
        cleaned['default_route'] = datum[10] is not None
        data.append(cleaned)
    return data


def network_in_use_on_host(context, network_id, host):
    fixed_ips = network_get_associated_fixed_ips(context, network_id, host)
    return len(fixed_ips) > 0


def _network_get_query(context, session=None):
    return model_query(context, models.Network, session=session,
                       read_deleted="no")


@require_admin_context
def network_get_by_uuid(context, uuid):
    result = _network_get_query(context).filter_by(uuid=uuid).first()

    if not result:
        raise exception.NetworkNotFoundForUUID(uuid=uuid)

    return result


@require_admin_context
def network_get_by_cidr(context, cidr):
    result = _network_get_query(context).\
                filter(or_(models.Network.cidr == cidr,
                           models.Network.cidr_v6 == cidr)).\
                first()

    if not result:
        raise exception.NetworkNotFoundForCidr(cidr=cidr)

    return result


@require_admin_context
def network_get_all_by_host(context, host):
    session = get_session()
    fixed_host_filter = or_(models.FixedIp.host == host,
            and_(models.FixedIp.instance_uuid != null(),
                 models.Instance.host == host))
    fixed_ip_query = model_query(context, models.FixedIp.network_id,
                                 base_model=models.FixedIp,
                                 session=session).\
                     outerjoin((models.Instance,
                                models.Instance.uuid ==
                                models.FixedIp.instance_uuid)).\
                     filter(fixed_host_filter)
    # NOTE(vish): return networks that have host set
    #             or that have a fixed ip with host set
    #             or that have an instance with host set
    host_filter = or_(models.Network.host == host,
                      models.Network.id.in_(fixed_ip_query.subquery()))
    return _network_get_query(context, session=session).\
                       filter(host_filter).\
                       all()


@require_admin_context
def network_set_host(context, network_id, host_id):
    session = get_session()
    with session.begin():
        network_ref = _network_get_query(context, session=session).\
                              filter_by(id=network_id).\
                              with_lockmode('update').\
                              first()

        if not network_ref:
            raise exception.NetworkNotFound(network_id=network_id)

        # NOTE(vish): if with_lockmode isn't supported, as in sqlite,
        #             then this has concurrency issues
        if not network_ref['host']:
            network_ref['host'] = host_id
            session.add(network_ref)

    return network_ref['host']


@require_context
def network_update(context, network_id, values):
    session = get_session()
    with session.begin():
        network_ref = _network_get(context, network_id, session=session)
        network_ref.update(values)
        try:
            network_ref.save(session=session)
        except db_exc.DBDuplicateEntry:
            raise exception.DuplicateVlan(vlan=values['vlan'])
        return network_ref


###################


@require_context
def quota_get(context, project_id, resource, user_id=None):
    model = models.ProjectUserQuota if user_id else models.Quota
    query = model_query(context, model).\
                    filter_by(project_id=project_id).\
                    filter_by(resource=resource)
    if user_id:
        query = query.filter_by(user_id=user_id)

    result = query.first()
    if not result:
        if user_id:
            raise exception.ProjectUserQuotaNotFound(project_id=project_id,
                                                     user_id=user_id)
        else:
            raise exception.ProjectQuotaNotFound(project_id=project_id)

    return result


@require_context
def quota_get_all_by_project_and_user(context, project_id, user_id):
    nova.context.authorize_project_context(context, project_id)

    user_quotas = model_query(context, models.ProjectUserQuota.resource,
                       models.ProjectUserQuota.hard_limit,
                       base_model=models.ProjectUserQuota).\
                   filter_by(project_id=project_id).\
                   filter_by(user_id=user_id).\
                   all()

    result = {'project_id': project_id, 'user_id': user_id}
    for user_quota in user_quotas:
        result[user_quota.resource] = user_quota.hard_limit

    return result


@require_context
def quota_get_all_by_project(context, project_id):
    nova.context.authorize_project_context(context, project_id)

    rows = model_query(context, models.Quota, read_deleted="no").\
                   filter_by(project_id=project_id).\
                   all()

    result = {'project_id': project_id}
    for row in rows:
        result[row.resource] = row.hard_limit

    return result


@require_context
def quota_get_all(context, project_id):
    nova.context.authorize_project_context(context, project_id)

    result = model_query(context, models.ProjectUserQuota).\
                   filter_by(project_id=project_id).\
                   all()

    return result


@require_admin_context
def quota_create(context, project_id, resource, limit, user_id=None):
    per_user = user_id and resource not in PER_PROJECT_QUOTAS
    quota_ref = models.ProjectUserQuota() if per_user else models.Quota()
    if per_user:
        quota_ref.user_id = user_id
    quota_ref.project_id = project_id
    quota_ref.resource = resource
    quota_ref.hard_limit = limit
    try:
        quota_ref.save()
    except db_exc.DBDuplicateEntry:
        raise exception.QuotaExists(project_id=project_id, resource=resource)
    return quota_ref


@require_admin_context
def quota_update(context, project_id, resource, limit, user_id=None):
    per_user = user_id and resource not in PER_PROJECT_QUOTAS
    model = models.ProjectUserQuota if per_user else models.Quota
    query = model_query(context, model).\
                filter_by(project_id=project_id).\
                filter_by(resource=resource)
    if per_user:
        query = query.filter_by(user_id=user_id)

    result = query.update({'hard_limit': limit})
    if not result:
        if per_user:
            raise exception.ProjectUserQuotaNotFound(project_id=project_id,
                                                     user_id=user_id)
        else:
            raise exception.ProjectQuotaNotFound(project_id=project_id)


###################


@require_context
def quota_class_get(context, class_name, resource):
    result = model_query(context, models.QuotaClass, read_deleted="no").\
                     filter_by(class_name=class_name).\
                     filter_by(resource=resource).\
                     first()

    if not result:
        raise exception.QuotaClassNotFound(class_name=class_name)

    return result


def quota_class_get_default(context):
    rows = model_query(context, models.QuotaClass, read_deleted="no").\
                   filter_by(class_name=_DEFAULT_QUOTA_NAME).\
                   all()

    result = {'class_name': _DEFAULT_QUOTA_NAME}
    for row in rows:
        result[row.resource] = row.hard_limit

    return result


@require_context
def quota_class_get_all_by_name(context, class_name):
    nova.context.authorize_quota_class_context(context, class_name)

    rows = model_query(context, models.QuotaClass, read_deleted="no").\
                   filter_by(class_name=class_name).\
                   all()

    result = {'class_name': class_name}
    for row in rows:
        result[row.resource] = row.hard_limit

    return result


@require_admin_context
def quota_class_create(context, class_name, resource, limit):
    quota_class_ref = models.QuotaClass()
    quota_class_ref.class_name = class_name
    quota_class_ref.resource = resource
    quota_class_ref.hard_limit = limit
    quota_class_ref.save()
    return quota_class_ref


@require_admin_context
def quota_class_update(context, class_name, resource, limit):
    result = model_query(context, models.QuotaClass, read_deleted="no").\
                     filter_by(class_name=class_name).\
                     filter_by(resource=resource).\
                     update({'hard_limit': limit})

    if not result:
        raise exception.QuotaClassNotFound(class_name=class_name)


###################


@require_context
def quota_usage_get(context, project_id, resource, user_id=None):
    query = model_query(context, models.QuotaUsage, read_deleted="no").\
                     filter_by(project_id=project_id).\
                     filter_by(resource=resource)
    if user_id:
        if resource not in PER_PROJECT_QUOTAS:
            result = query.filter_by(user_id=user_id).first()
        else:
            result = query.filter_by(user_id=None).first()
    else:
        result = query.first()

    if not result:
        raise exception.QuotaUsageNotFound(project_id=project_id)

    return result


def _quota_usage_get_all(context, project_id, user_id=None):
    nova.context.authorize_project_context(context, project_id)
    query = model_query(context, models.QuotaUsage, read_deleted="no").\
                   filter_by(project_id=project_id)
    result = {'project_id': project_id}
    if user_id:
        query = query.filter(or_(models.QuotaUsage.user_id == user_id,
                                 models.QuotaUsage.user_id == null()))
        result['user_id'] = user_id

    rows = query.all()
    for row in rows:
        if row.resource in result:
            result[row.resource]['in_use'] += row.in_use
            result[row.resource]['reserved'] += row.reserved
        else:
            result[row.resource] = dict(in_use=row.in_use,
                                        reserved=row.reserved)

    return result


@require_context
def quota_usage_get_all_by_project_and_user(context, project_id, user_id):
    return _quota_usage_get_all(context, project_id, user_id=user_id)


@require_context
def quota_usage_get_all_by_project(context, project_id):
    return _quota_usage_get_all(context, project_id)


def _quota_usage_create(context, project_id, user_id, resource, in_use,
                        reserved, until_refresh, session=None):
    quota_usage_ref = models.QuotaUsage()
    quota_usage_ref.project_id = project_id
    quota_usage_ref.user_id = user_id
    quota_usage_ref.resource = resource
    quota_usage_ref.in_use = in_use
    quota_usage_ref.reserved = reserved
    quota_usage_ref.until_refresh = until_refresh
    # updated_at is needed for judgement of max_age
    quota_usage_ref.updated_at = timeutils.utcnow()

    quota_usage_ref.save(session=session)

    return quota_usage_ref


@require_admin_context
def quota_usage_update(context, project_id, user_id, resource, **kwargs):
    updates = {}

    for key in ['in_use', 'reserved', 'until_refresh']:
        if key in kwargs:
            updates[key] = kwargs[key]

    result = model_query(context, models.QuotaUsage, read_deleted="no").\
                     filter_by(project_id=project_id).\
                     filter_by(resource=resource).\
                     filter(or_(models.QuotaUsage.user_id == user_id,
                                models.QuotaUsage.user_id == null())).\
                     update(updates)

    if not result:
        raise exception.QuotaUsageNotFound(project_id=project_id)


###################


def _reservation_create(context, uuid, usage, project_id, user_id, resource,
                        delta, expire, session=None):
    reservation_ref = models.Reservation()
    reservation_ref.uuid = uuid
    reservation_ref.usage_id = usage['id']
    reservation_ref.project_id = project_id
    reservation_ref.user_id = user_id
    reservation_ref.resource = resource
    reservation_ref.delta = delta
    reservation_ref.expire = expire
    reservation_ref.save(session=session)
    return reservation_ref


###################


# NOTE(johannes): The quota code uses SQL locking to ensure races don't
# cause under or over counting of resources. To avoid deadlocks, this
# code always acquires the lock on quota_usages before acquiring the lock
# on reservations.

def _get_project_user_quota_usages(context, session, project_id,
                                   user_id):
    rows = model_query(context, models.QuotaUsage,
                       read_deleted="no",
                       session=session).\
                   filter_by(project_id=project_id).\
                   with_lockmode('update').\
                   all()
    proj_result = dict()
    user_result = dict()
    # Get the total count of in_use,reserved
    for row in rows:
        proj_result.setdefault(row.resource,
                               dict(in_use=0, reserved=0, total=0))
        proj_result[row.resource]['in_use'] += row.in_use
        proj_result[row.resource]['reserved'] += row.reserved
        proj_result[row.resource]['total'] += (row.in_use + row.reserved)
        if row.user_id is None or row.user_id == user_id:
            user_result[row.resource] = row
    return proj_result, user_result


@require_context
@_retry_on_deadlock
def quota_reserve(context, resources, project_quotas, user_quotas, deltas,
                  expire, until_refresh, max_age, project_id=None,
                  user_id=None):
    elevated = context.elevated()
    session = get_session()
    with session.begin():

        if project_id is None:
            project_id = context.project_id
        if user_id is None:
            user_id = context.user_id

        # Get the current usages
        project_usages, user_usages = _get_project_user_quota_usages(
                context, session, project_id, user_id)

        # Handle usage refresh
        work = set(deltas.keys())
        while work:
            resource = work.pop()

            # Do we need to refresh the usage?
            refresh = False
            if ((resource not in PER_PROJECT_QUOTAS) and
                    (resource not in user_usages)):
                user_usages[resource] = _quota_usage_create(elevated,
                                                      project_id,
                                                      user_id,
                                                      resource,
                                                      0, 0,
                                                      until_refresh or None,
                                                      session=session)
                refresh = True
            elif ((resource in PER_PROJECT_QUOTAS) and
                    (resource not in user_usages)):
                user_usages[resource] = _quota_usage_create(elevated,
                                                      project_id,
                                                      None,
                                                      resource,
                                                      0, 0,
                                                      until_refresh or None,
                                                      session=session)
                refresh = True
            elif user_usages[resource].in_use < 0:
                # Negative in_use count indicates a desync, so try to
                # heal from that...
                refresh = True
            elif user_usages[resource].until_refresh is not None:
                user_usages[resource].until_refresh -= 1
                if user_usages[resource].until_refresh <= 0:
                    refresh = True
            elif max_age and (timeutils.utcnow() -
                    user_usages[resource].updated_at).seconds >= max_age:
                refresh = True

            # OK, refresh the usage
            if refresh:
                # Grab the sync routine
                sync = QUOTA_SYNC_FUNCTIONS[resources[resource].sync]

                updates = sync(elevated, project_id, user_id, session)
                for res, in_use in updates.items():
                    # Make sure we have a destination for the usage!
                    if ((res not in PER_PROJECT_QUOTAS) and
                            (res not in user_usages)):
                        user_usages[res] = _quota_usage_create(elevated,
                                                         project_id,
                                                         user_id,
                                                         res,
                                                         0, 0,
                                                         until_refresh or None,
                                                         session=session)
                    if ((res in PER_PROJECT_QUOTAS) and
                            (res not in user_usages)):
                        user_usages[res] = _quota_usage_create(elevated,
                                                         project_id,
                                                         None,
                                                         res,
                                                         0, 0,
                                                         until_refresh or None,
                                                         session=session)

                    if user_usages[res].in_use != in_use:
                        LOG.debug('quota_usages out of sync, updating. '
                                  'project_id: %(project_id)s, '
                                  'user_id: %(user_id)s, '
                                  'resource: %(res)s, '
                                  'tracked usage: %(tracked_use)s, '
                                  'actual usage: %(in_use)s',
                            {'project_id': project_id,
                             'user_id': user_id,
                             'res': res,
                             'tracked_use': user_usages[res].in_use,
                             'in_use': in_use})

                    # Update the usage
                    user_usages[res].in_use = in_use
                    user_usages[res].until_refresh = until_refresh or None

                    # Because more than one resource may be refreshed
                    # by the call to the sync routine, and we don't
                    # want to double-sync, we make sure all refreshed
                    # resources are dropped from the work set.
                    work.discard(res)

                    # NOTE(Vek): We make the assumption that the sync
                    #            routine actually refreshes the
                    #            resources that it is the sync routine
                    #            for.  We don't check, because this is
                    #            a best-effort mechanism.

        # Check for deltas that would go negative
        unders = [res for res, delta in deltas.items()
                  if delta < 0 and
                  delta + user_usages[res].in_use < 0]

        # Now, let's check the quotas
        # NOTE(Vek): We're only concerned about positive increments.
        #            If a project has gone over quota, we want them to
        #            be able to reduce their usage without any
        #            problems.
        for key, value in user_usages.items():
            if key not in project_usages:
                project_usages[key] = value
        overs = [res for res, delta in deltas.items()
                 if user_quotas[res] >= 0 and delta >= 0 and
                 (project_quotas[res] < delta +
                  project_usages[res]['total'] or
                  user_quotas[res] < delta +
                  user_usages[res].total)]

        # NOTE(Vek): The quota check needs to be in the transaction,
        #            but the transaction doesn't fail just because
        #            we're over quota, so the OverQuota raise is
        #            outside the transaction.  If we did the raise
        #            here, our usage updates would be discarded, but
        #            they're not invalidated by being over-quota.

        # Create the reservations
        if not overs:
            reservations = []
            for res, delta in deltas.items():
                reservation = _reservation_create(elevated,
                                                 str(uuid.uuid4()),
                                                 user_usages[res],
                                                 project_id,
                                                 user_id,
                                                 res, delta, expire,
                                                 session=session)
                reservations.append(reservation.uuid)

                # Also update the reserved quantity
                # NOTE(Vek): Again, we are only concerned here about
                #            positive increments.  Here, though, we're
                #            worried about the following scenario:
                #
                #            1) User initiates resize down.
                #            2) User allocates a new instance.
                #            3) Resize down fails or is reverted.
                #            4) User is now over quota.
                #
                #            To prevent this, we only update the
                #            reserved value if the delta is positive.
                if delta > 0:
                    user_usages[res].reserved += delta

        # Apply updates to the usages table
        for usage_ref in user_usages.values():
            session.add(usage_ref)

    if unders:
        LOG.warning(_("Change will make usage less than 0 for the following "
                      "resources: %s"), unders)
    if overs:
        if project_quotas == user_quotas:
            usages = project_usages
        else:
            usages = user_usages
        usages = dict((k, dict(in_use=v['in_use'], reserved=v['reserved']))
                      for k, v in usages.items())
        headroom = dict((res, user_quotas[res] -
                             (usages[res]['in_use'] + usages[res]['reserved']))
                        for res in user_quotas.keys())

        # If quota_cores is unlimited [-1]:
        # - set cores headroom based on instances headroom:
        if user_quotas.get('cores') == -1:
            if deltas['cores']:
                hc = headroom['instances'] * deltas['cores']
                headroom['cores'] = hc / deltas['instances']
            else:
                headroom['cores'] = headroom['instances']

        # If quota_ram is unlimited [-1]:
        # - set ram headroom based on instances headroom:
        if user_quotas.get('ram') == -1:
            if deltas['ram']:
                hr = headroom['instances'] * deltas['ram']
                headroom['ram'] = hr / deltas['instances']
            else:
                headroom['ram'] = headroom['instances']
        raise exception.OverQuota(overs=sorted(overs), quotas=user_quotas,
                                  usages=usages, headroom=headroom)

    return reservations


def _quota_reservations_query(session, context, reservations):
    """Return the relevant reservations."""

    # Get the listed reservations
    return model_query(context, models.Reservation,
                       read_deleted="no",
                       session=session).\
                   filter(models.Reservation.uuid.in_(reservations)).\
                   with_lockmode('update')


@require_context
@_retry_on_deadlock
def reservation_commit(context, reservations, project_id=None, user_id=None):
    session = get_session()
    with session.begin():
        _project_usages, user_usages = _get_project_user_quota_usages(
                context, session, project_id, user_id)
        reservation_query = _quota_reservations_query(session, context,
                                                      reservations)
        for reservation in reservation_query.all():
            usage = user_usages[reservation.resource]
            if reservation.delta >= 0:
                usage.reserved -= reservation.delta
            usage.in_use += reservation.delta
        reservation_query.soft_delete(synchronize_session=False)


@require_context
@_retry_on_deadlock
def reservation_rollback(context, reservations, project_id=None, user_id=None):
    session = get_session()
    with session.begin():
        _project_usages, user_usages = _get_project_user_quota_usages(
                context, session, project_id, user_id)
        reservation_query = _quota_reservations_query(session, context,
                                                      reservations)
        for reservation in reservation_query.all():
            usage = user_usages[reservation.resource]
            if reservation.delta >= 0:
                usage.reserved -= reservation.delta
        reservation_query.soft_delete(synchronize_session=False)


@require_admin_context
def quota_destroy_all_by_project_and_user(context, project_id, user_id):
    session = get_session()
    with session.begin():
        model_query(context, models.ProjectUserQuota, session=session,
                    read_deleted="no").\
                filter_by(project_id=project_id).\
                filter_by(user_id=user_id).\
                soft_delete(synchronize_session=False)

        model_query(context, models.QuotaUsage,
                    session=session, read_deleted="no").\
                filter_by(project_id=project_id).\
                filter_by(user_id=user_id).\
                soft_delete(synchronize_session=False)

        model_query(context, models.Reservation,
                    session=session, read_deleted="no").\
                filter_by(project_id=project_id).\
                filter_by(user_id=user_id).\
                soft_delete(synchronize_session=False)


@require_admin_context
def quota_destroy_all_by_project(context, project_id):
    session = get_session()
    with session.begin():
        model_query(context, models.Quota, session=session,
                    read_deleted="no").\
                filter_by(project_id=project_id).\
                soft_delete(synchronize_session=False)

        model_query(context, models.ProjectUserQuota, session=session,
                    read_deleted="no").\
                filter_by(project_id=project_id).\
                soft_delete(synchronize_session=False)

        model_query(context, models.QuotaUsage,
                    session=session, read_deleted="no").\
                filter_by(project_id=project_id).\
                soft_delete(synchronize_session=False)

        model_query(context, models.Reservation,
                    session=session, read_deleted="no").\
                filter_by(project_id=project_id).\
                soft_delete(synchronize_session=False)


@require_admin_context
@_retry_on_deadlock
def reservation_expire(context):
    session = get_session()
    with session.begin():
        current_time = timeutils.utcnow()
        reservation_query = model_query(context, models.Reservation,
                                        session=session, read_deleted="no").\
                            filter(models.Reservation.expire < current_time)

        for reservation in reservation_query.join(models.QuotaUsage).all():
            if reservation.delta >= 0:
                reservation.usage.reserved -= reservation.delta
                session.add(reservation.usage)

        reservation_query.soft_delete(synchronize_session=False)


###################


def _ec2_volume_get_query(context, session=None):
    return model_query(context, models.VolumeIdMapping,
                       session=session, read_deleted='yes')


def _ec2_snapshot_get_query(context, session=None):
    return model_query(context, models.SnapshotIdMapping,
                       session=session, read_deleted='yes')


@require_context
def ec2_volume_create(context, volume_uuid, id=None):
    """Create ec2 compatible volume by provided uuid."""
    ec2_volume_ref = models.VolumeIdMapping()
    ec2_volume_ref.update({'uuid': volume_uuid})
    if id is not None:
        ec2_volume_ref.update({'id': id})

    ec2_volume_ref.save()

    return ec2_volume_ref


@require_context
def ec2_volume_get_by_uuid(context, volume_uuid):
    result = _ec2_volume_get_query(context).\
                    filter_by(uuid=volume_uuid).\
                    first()

    if not result:
        raise exception.VolumeNotFound(volume_id=volume_uuid)

    return result


@require_context
def ec2_volume_get_by_id(context, volume_id):
    result = _ec2_volume_get_query(context).\
                    filter_by(id=volume_id).\
                    first()

    if not result:
        raise exception.VolumeNotFound(volume_id=volume_id)

    return result


@require_context
def ec2_snapshot_create(context, snapshot_uuid, id=None):
    """Create ec2 compatible snapshot by provided uuid."""
    ec2_snapshot_ref = models.SnapshotIdMapping()
    ec2_snapshot_ref.update({'uuid': snapshot_uuid})
    if id is not None:
        ec2_snapshot_ref.update({'id': id})

    ec2_snapshot_ref.save()

    return ec2_snapshot_ref


@require_context
def ec2_snapshot_get_by_ec2_id(context, ec2_id):
    result = _ec2_snapshot_get_query(context).\
                    filter_by(id=ec2_id).\
                    first()

    if not result:
        raise exception.SnapshotNotFound(snapshot_id=ec2_id)

    return result


@require_context
def ec2_snapshot_get_by_uuid(context, snapshot_uuid):
    result = _ec2_snapshot_get_query(context).\
                    filter_by(uuid=snapshot_uuid).\
                    first()

    if not result:
        raise exception.SnapshotNotFound(snapshot_id=snapshot_uuid)

    return result


###################


def _block_device_mapping_get_query(context, session=None,
        columns_to_join=None, use_slave=False):
    if columns_to_join is None:
        columns_to_join = []

    query = model_query(context, models.BlockDeviceMapping,
                        session=session, use_slave=use_slave)

    for column in columns_to_join:
        query = query.options(joinedload(column))

    return query


def _scrub_empty_str_values(dct, keys_to_scrub):
    """Remove any keys found in sequence keys_to_scrub from the dict
    if they have the value ''.
    """
    for key in keys_to_scrub:
        if key in dct and dct[key] == '':
            del dct[key]


def _from_legacy_values(values, legacy, allow_updates=False):
    if legacy:
        if allow_updates and block_device.is_safe_for_update(values):
            return values
        else:
            return block_device.BlockDeviceDict.from_legacy(values)
    else:
        return values


@require_context
def block_device_mapping_create(context, values, legacy=True):
    _scrub_empty_str_values(values, ['volume_size'])
    values = _from_legacy_values(values, legacy)
    bdm_ref = models.BlockDeviceMapping()
    bdm_ref.update(values)
    bdm_ref.save()
    return bdm_ref


@require_context
def block_device_mapping_update(context, bdm_id, values, legacy=True):
    _scrub_empty_str_values(values, ['volume_size'])
    values = _from_legacy_values(values, legacy, allow_updates=True)
    query = _block_device_mapping_get_query(context).filter_by(id=bdm_id)
    query.update(values)
    return query.first()


def block_device_mapping_update_or_create(context, values, legacy=True):
    _scrub_empty_str_values(values, ['volume_size'])
    values = _from_legacy_values(values, legacy, allow_updates=True)

    session = get_session()
    with session.begin():
        result = None
        # NOTE(xqueralt): Only update a BDM when device_name was provided. We
        # allow empty device names so they will be set later by the manager.
        if values['device_name']:
            query = _block_device_mapping_get_query(context, session=session)
            result = query.filter_by(instance_uuid=values['instance_uuid'],
                                     device_name=values['device_name']).first()

        if result:
            result.update(values)
        else:
            # Either the device_name doesn't exist in the database yet, or no
            # device_name was provided. Both cases mean creating a new BDM.
            result = models.BlockDeviceMapping(**values)
            result.save(session=session)

        # NOTE(xqueralt): Prevent from having multiple swap devices for the
        # same instance. This will delete all the existing ones.
        if block_device.new_format_is_swap(values):
            query = _block_device_mapping_get_query(context, session=session)
            query = query.filter_by(instance_uuid=values['instance_uuid'],
                                    source_type='blank', guest_format='swap')
            query = query.filter(models.BlockDeviceMapping.id != result.id)
            query.soft_delete()

        return result


@require_context
def block_device_mapping_get_all_by_instance(context, instance_uuid,
                                             use_slave=False):
    return _block_device_mapping_get_query(context, use_slave=use_slave).\
                 filter_by(instance_uuid=instance_uuid).\
                 all()


@require_context
def block_device_mapping_get_by_volume_id(context, volume_id,
        columns_to_join=None):
    return _block_device_mapping_get_query(context,
            columns_to_join=columns_to_join).\
                 filter_by(volume_id=volume_id).\
                 first()


@require_context
def block_device_mapping_destroy(context, bdm_id):
    _block_device_mapping_get_query(context).\
            filter_by(id=bdm_id).\
            soft_delete()


@require_context
def block_device_mapping_destroy_by_instance_and_volume(context, instance_uuid,
                                                        volume_id):
    _block_device_mapping_get_query(context).\
            filter_by(instance_uuid=instance_uuid).\
            filter_by(volume_id=volume_id).\
            soft_delete()


@require_context
def block_device_mapping_destroy_by_instance_and_device(context, instance_uuid,
                                                        device_name):
    _block_device_mapping_get_query(context).\
            filter_by(instance_uuid=instance_uuid).\
            filter_by(device_name=device_name).\
            soft_delete()


###################

def _security_group_create(context, values, session=None):
    security_group_ref = models.SecurityGroup()
    # FIXME(devcamcar): Unless I do this, rules fails with lazy load exception
    # once save() is called.  This will get cleaned up in next orm pass.
    security_group_ref.rules
    security_group_ref.update(values)
    try:
        security_group_ref.save(session=session)
    except db_exc.DBDuplicateEntry:
        raise exception.SecurityGroupExists(
                project_id=values['project_id'],
                security_group_name=values['name'])
    return security_group_ref


def _security_group_get_query(context, session=None, read_deleted=None,
                              project_only=False, join_rules=True):
    query = model_query(context, models.SecurityGroup, session=session,
            read_deleted=read_deleted, project_only=project_only)
    if join_rules:
        query = query.options(joinedload_all('rules.grantee_group'))
    return query


def _security_group_get_by_names(context, session, project_id, group_names):
    """Get security group models for a project by a list of names.
    Raise SecurityGroupNotFoundForProject for a name not found.
    """
    query = _security_group_get_query(context, session=session,
                                      read_deleted="no", join_rules=False).\
            filter_by(project_id=project_id).\
            filter(models.SecurityGroup.name.in_(group_names))
    sg_models = query.all()
    if len(sg_models) == len(group_names):
        return sg_models
    # Find the first one missing and raise
    group_names_from_models = [x.name for x in sg_models]
    for group_name in group_names:
        if group_name not in group_names_from_models:
            raise exception.SecurityGroupNotFoundForProject(
                    project_id=project_id, security_group_id=group_name)
    # Not Reached


@require_context
def security_group_get_all(context):
    return _security_group_get_query(context).all()


@require_context
def security_group_get(context, security_group_id, columns_to_join=None):
    query = _security_group_get_query(context, project_only=True).\
                    filter_by(id=security_group_id)

    if columns_to_join is None:
        columns_to_join = []
    for column in columns_to_join:
        if column.startswith('instances'):
            query = query.options(joinedload_all(column))

    result = query.first()
    if not result:
        raise exception.SecurityGroupNotFound(
                security_group_id=security_group_id)

    return result


@require_context
def security_group_get_by_name(context, project_id, group_name,
                               columns_to_join=None):
    query = _security_group_get_query(context,
                                      read_deleted="no", join_rules=False).\
            filter_by(project_id=project_id).\
            filter_by(name=group_name)

    if columns_to_join is None:
        columns_to_join = ['instances', 'rules.grantee_group']

    for column in columns_to_join:
        query = query.options(joinedload_all(column))

    result = query.first()
    if not result:
        raise exception.SecurityGroupNotFoundForProject(
                project_id=project_id, security_group_id=group_name)

    return result


@require_context
def security_group_get_by_project(context, project_id):
    return _security_group_get_query(context, read_deleted="no").\
                        filter_by(project_id=project_id).\
                        all()


@require_context
def security_group_get_by_instance(context, instance_uuid):
    return _security_group_get_query(context, read_deleted="no").\
                   join(models.SecurityGroup.instances).\
                   filter_by(uuid=instance_uuid).\
                   all()


@require_context
def security_group_in_use(context, group_id):
    session = get_session()
    with session.begin():
        # Are there any instances that haven't been deleted
        # that include this group?
        inst_assoc = model_query(context,
                                 models.SecurityGroupInstanceAssociation,
                                 read_deleted="no", session=session).\
                        filter_by(security_group_id=group_id).\
                        all()
        for ia in inst_assoc:
            num_instances = model_query(context, models.Instance,
                                        session=session, read_deleted="no").\
                        filter_by(uuid=ia.instance_uuid).\
                        count()
            if num_instances:
                return True

    return False


@require_context
def security_group_create(context, values):
    return _security_group_create(context, values)


@require_context
def security_group_update(context, security_group_id, values,
                          columns_to_join=None):
    session = get_session()
    with session.begin():
        query = model_query(context, models.SecurityGroup,
                         session=session).filter_by(id=security_group_id)
        if columns_to_join:
            for column in columns_to_join:
                query = query.options(joinedload_all(column))
        security_group_ref = query.first()

        if not security_group_ref:
            raise exception.SecurityGroupNotFound(
                    security_group_id=security_group_id)
        security_group_ref.update(values)
        name = security_group_ref['name']
        project_id = security_group_ref['project_id']
        try:
            security_group_ref.save(session=session)
        except db_exc.DBDuplicateEntry:
            raise exception.SecurityGroupExists(
                    project_id=project_id,
                    security_group_name=name)
    return security_group_ref


def security_group_ensure_default(context):
    """Ensure default security group exists for a project_id."""

    try:
        return _security_group_ensure_default(context)
    except exception.SecurityGroupExists:
        # NOTE(rpodolyaka): a concurrent transaction has succeeded first,
        # suppress the error and proceed
        return security_group_get_by_name(context, context.project_id,
                                          'default')


def _security_group_ensure_default(context, session=None):
    if session is None:
        session = get_session()

    with session.begin(subtransactions=True):
        try:
            default_group = _security_group_get_by_names(context,
                                                         session,
                                                         context.project_id,
                                                         ['default'])[0]
        except exception.NotFound:
            values = {'name': 'default',
                      'description': 'default',
                      'user_id': context.user_id,
                      'project_id': context.project_id}
            default_group = _security_group_create(context, values,
                                                   session=session)
            usage = model_query(context, models.QuotaUsage,
                                read_deleted="no", session=session).\
                     filter_by(project_id=context.project_id).\
                     filter_by(user_id=context.user_id).\
                     filter_by(resource='security_groups')
            # Create quota usage for auto created default security group
            if not usage.first():
                elevated = context.elevated()
                _quota_usage_create(elevated,
                                    context.project_id,
                                    context.user_id,
                                    'security_groups',
                                    1, 0,
                                    None,
                                    session=session)
            else:
                usage.update({'in_use': int(usage.first().in_use) + 1})

            default_rules = _security_group_rule_get_default_query(context,
                                session=session).all()
            for default_rule in default_rules:
                # This is suboptimal, it should be programmatic to know
                # the values of the default_rule
                rule_values = {'protocol': default_rule.protocol,
                               'from_port': default_rule.from_port,
                               'to_port': default_rule.to_port,
                               'cidr': default_rule.cidr,
                               'parent_group_id': default_group.id,
                }
                _security_group_rule_create(context,
                                            rule_values,
                                            session=session)
        return default_group


@require_context
def security_group_destroy(context, security_group_id):
    session = get_session()
    with session.begin():
        model_query(context, models.SecurityGroup,
                    session=session).\
                filter_by(id=security_group_id).\
                soft_delete()
        model_query(context, models.SecurityGroupInstanceAssociation,
                    session=session).\
                filter_by(security_group_id=security_group_id).\
                soft_delete()
        model_query(context, models.SecurityGroupIngressRule,
                    session=session).\
                filter_by(group_id=security_group_id).\
                soft_delete()
        model_query(context, models.SecurityGroupIngressRule,
                    session=session).\
                filter_by(parent_group_id=security_group_id).\
                soft_delete()


def _security_group_count_by_project_and_user(context, project_id, user_id,
                                             session=None):
    nova.context.authorize_project_context(context, project_id)
    return model_query(context, models.SecurityGroup, read_deleted="no",
                       session=session).\
                   filter_by(project_id=project_id).\
                   filter_by(user_id=user_id).\
                   count()


###################


def _security_group_rule_create(context, values, session=None):
    security_group_rule_ref = models.SecurityGroupIngressRule()
    security_group_rule_ref.update(values)
    security_group_rule_ref.save(session=session)
    return security_group_rule_ref


def _security_group_rule_get_query(context, session=None):
    return model_query(context, models.SecurityGroupIngressRule,
                       session=session)


@require_context
def security_group_rule_get(context, security_group_rule_id):
    result = (_security_group_rule_get_query(context).
                         filter_by(id=security_group_rule_id).
                         first())

    if not result:
        raise exception.SecurityGroupNotFoundForRule(
                                               rule_id=security_group_rule_id)

    return result


@require_context
def security_group_rule_get_by_security_group(context, security_group_id,
                                              columns_to_join=None):
    if columns_to_join is None:
        columns_to_join = ['grantee_group.instances.system_metadata',
                           'grantee_group.instances.info_cache']
    query = (_security_group_rule_get_query(context).
             filter_by(parent_group_id=security_group_id))
    for column in columns_to_join:
        query = query.options(joinedload_all(column))
    return query.all()


@require_context
def security_group_rule_get_by_security_group_grantee(context,
                                                      security_group_id):

    return (_security_group_rule_get_query(context).
                         filter_by(group_id=security_group_id).
                         all())


@require_context
def security_group_rule_create(context, values):
    return _security_group_rule_create(context, values)


@require_context
def security_group_rule_destroy(context, security_group_rule_id):
    count = (_security_group_rule_get_query(context).
                    filter_by(id=security_group_rule_id).
                    soft_delete())
    if count == 0:
        raise exception.SecurityGroupNotFoundForRule(
                                            rule_id=security_group_rule_id)


@require_context
def security_group_rule_count_by_group(context, security_group_id):
    return (model_query(context, models.SecurityGroupIngressRule,
                   read_deleted="no").
                   filter_by(parent_group_id=security_group_id).
                   count())

#
###################


def _security_group_rule_get_default_query(context, session=None):
    return model_query(context, models.SecurityGroupIngressDefaultRule,
                       session=session)


@require_context
def security_group_default_rule_get(context, security_group_rule_default_id):
    result = _security_group_rule_get_default_query(context).\
                        filter_by(id=security_group_rule_default_id).\
                        first()

    if not result:
        raise exception.SecurityGroupDefaultRuleNotFound(
                                        rule_id=security_group_rule_default_id)

    return result


@require_admin_context
def security_group_default_rule_destroy(context,
                                        security_group_rule_default_id):
    session = get_session()
    with session.begin():
        count = _security_group_rule_get_default_query(context,
                                                       session=session).\
                            filter_by(id=security_group_rule_default_id).\
                            soft_delete()
        if count == 0:
            raise exception.SecurityGroupDefaultRuleNotFound(
                                        rule_id=security_group_rule_default_id)


@require_admin_context
def security_group_default_rule_create(context, values):
    security_group_default_rule_ref = models.SecurityGroupIngressDefaultRule()
    security_group_default_rule_ref.update(values)
    security_group_default_rule_ref.save()
    return security_group_default_rule_ref


@require_context
def security_group_default_rule_list(context):
    return _security_group_rule_get_default_query(context).\
                                    all()


###################


@require_admin_context
def provider_fw_rule_create(context, rule):
    fw_rule_ref = models.ProviderFirewallRule()
    fw_rule_ref.update(rule)
    fw_rule_ref.save()
    return fw_rule_ref


@require_admin_context
def provider_fw_rule_get_all(context):
    return model_query(context, models.ProviderFirewallRule).all()


@require_admin_context
def provider_fw_rule_destroy(context, rule_id):
    session = get_session()
    with session.begin():
        session.query(models.ProviderFirewallRule).\
                filter_by(id=rule_id).\
                soft_delete()


###################


@require_context
def project_get_networks(context, project_id, associate=True):
    # NOTE(tr3buchet): as before this function will associate
    # a project with a network if it doesn't have one and
    # associate is true
    result = model_query(context, models.Network, read_deleted="no").\
                     filter_by(project_id=project_id).\
                     all()

    if not result:
        if not associate:
            return []

        return [network_associate(context, project_id)]

    return result


###################


@require_admin_context
def migration_create(context, values):
    migration = models.Migration()
    migration.update(values)
    migration.save()
    return migration


@require_admin_context
def migration_update(context, id, values):
    session = get_session()
    with session.begin():
        migration = _migration_get(context, id, session=session)
        migration.update(values)

    return migration


def _migration_get(context, id, session=None):
    result = model_query(context, models.Migration, session=session,
                         read_deleted="yes").\
                     filter_by(id=id).\
                     first()

    if not result:
        raise exception.MigrationNotFound(migration_id=id)

    return result


@require_admin_context
def migration_get(context, id):
    return _migration_get(context, id)


@require_admin_context
def migration_get_by_instance_and_status(context, instance_uuid, status):
    result = model_query(context, models.Migration, read_deleted="yes").\
                     filter_by(instance_uuid=instance_uuid).\
                     filter_by(status=status).\
                     first()

    if not result:
        raise exception.MigrationNotFoundByStatus(instance_id=instance_uuid,
                                                  status=status)

    return result


@require_admin_context
def migration_get_unconfirmed_by_dest_compute(context, confirm_window,
                                              dest_compute, use_slave=False):
    confirm_window = (timeutils.utcnow() -
                      datetime.timedelta(seconds=confirm_window))

    return model_query(context, models.Migration, read_deleted="yes",
                       use_slave=use_slave).\
             filter(models.Migration.updated_at <= confirm_window).\
             filter_by(status="finished").\
             filter_by(dest_compute=dest_compute).\
             all()


@require_admin_context
def migration_get_in_progress_by_host_and_node(context, host, node):

    return model_query(context, models.Migration).\
            filter(or_(and_(models.Migration.source_compute == host,
                            models.Migration.source_node == node),
                       and_(models.Migration.dest_compute == host,
                            models.Migration.dest_node == node))).\
            filter(~models.Migration.status.in_(['confirmed', 'reverted',
                                                 'error'])).\
            options(joinedload_all('instance.system_metadata')).\
            all()


@require_admin_context
def migration_get_all_by_filters(context, filters):
    query = model_query(context, models.Migration)
    if "status" in filters:
        query = query.filter(models.Migration.status == filters["status"])
    if "host" in filters:
        host = filters["host"]
        query = query.filter(or_(models.Migration.source_compute == host,
                                 models.Migration.dest_compute == host))
    return query.all()


##################


def console_pool_create(context, values):
    pool = models.ConsolePool()
    pool.update(values)
    try:
        pool.save()
    except db_exc.DBDuplicateEntry:
        raise exception.ConsolePoolExists(
            host=values["host"],
            console_type=values["console_type"],
            compute_host=values["compute_host"],
        )
    return pool


def console_pool_get_by_host_type(context, compute_host, host,
                                  console_type):

    result = model_query(context, models.ConsolePool, read_deleted="no").\
                   filter_by(host=host).\
                   filter_by(console_type=console_type).\
                   filter_by(compute_host=compute_host).\
                   options(joinedload('consoles')).\
                   first()

    if not result:
        raise exception.ConsolePoolNotFoundForHostType(
                host=host, console_type=console_type,
                compute_host=compute_host)

    return result


def console_pool_get_all_by_host_type(context, host, console_type):
    return model_query(context, models.ConsolePool, read_deleted="no").\
                   filter_by(host=host).\
                   filter_by(console_type=console_type).\
                   options(joinedload('consoles')).\
                   all()


def console_create(context, values):
    console = models.Console()
    console.update(values)
    console.save()
    return console


def console_delete(context, console_id):
    session = get_session()
    with session.begin():
        # NOTE(mdragon): consoles are meant to be transient.
        session.query(models.Console).\
                filter_by(id=console_id).\
                delete()


def console_get_by_pool_instance(context, pool_id, instance_uuid):
    result = model_query(context, models.Console, read_deleted="yes").\
                   filter_by(pool_id=pool_id).\
                   filter_by(instance_uuid=instance_uuid).\
                   options(joinedload('pool')).\
                   first()

    if not result:
        raise exception.ConsoleNotFoundInPoolForInstance(
                pool_id=pool_id, instance_uuid=instance_uuid)

    return result


def console_get_all_by_instance(context, instance_uuid, columns_to_join=None):
    query = model_query(context, models.Console, read_deleted="yes").\
                filter_by(instance_uuid=instance_uuid)
    if columns_to_join:
        for column in columns_to_join:
            query = query.options(joinedload(column))
    return query.all()


def console_get(context, console_id, instance_uuid=None):
    query = model_query(context, models.Console, read_deleted="yes").\
                    filter_by(id=console_id).\
                    options(joinedload('pool'))

    if instance_uuid is not None:
        query = query.filter_by(instance_uuid=instance_uuid)

    result = query.first()

    if not result:
        if instance_uuid:
            raise exception.ConsoleNotFoundForInstance(
                    console_id=console_id, instance_uuid=instance_uuid)
        else:
            raise exception.ConsoleNotFound(console_id=console_id)

    return result


##################


@require_admin_context
def flavor_create(context, values, projects=None):
    """Create a new instance type. In order to pass in extra specs,
    the values dict should contain a 'extra_specs' key/value pair:

    {'extra_specs' : {'k1': 'v1', 'k2': 'v2', ...}}

    """
    specs = values.get('extra_specs')
    specs_refs = []
    if specs:
        for k, v in specs.iteritems():
            specs_ref = models.InstanceTypeExtraSpecs()
            specs_ref['key'] = k
            specs_ref['value'] = v
            specs_refs.append(specs_ref)

    values['extra_specs'] = specs_refs
    instance_type_ref = models.InstanceTypes()
    instance_type_ref.update(values)

    if projects is None:
        projects = []

    session = get_session()
    with session.begin():
        try:
            instance_type_ref.save()
        except db_exc.DBDuplicateEntry as e:
            if 'flavorid' in e.columns:
                raise exception.FlavorIdExists(flavor_id=values['flavorid'])
            raise exception.FlavorExists(name=values['name'])
        except Exception as e:
            raise db_exc.DBError(e)
        for project in set(projects):
            access_ref = models.InstanceTypeProjects()
            access_ref.update({"instance_type_id": instance_type_ref.id,
                               "project_id": project})
            access_ref.save()

    return _dict_with_extra_specs(instance_type_ref)


def _dict_with_extra_specs(inst_type_query):
    """Takes an instance or instance type query returned
    by sqlalchemy and returns it as a dictionary, converting the
    extra_specs entry from a list of dicts:

    'extra_specs' : [{'key': 'k1', 'value': 'v1', ...}, ...]

    to a single dict:

    'extra_specs' : {'k1': 'v1'}

    """
    inst_type_dict = dict(inst_type_query)
    extra_specs = dict([(x['key'], x['value'])
                        for x in inst_type_query['extra_specs']])
    inst_type_dict['extra_specs'] = extra_specs
    return inst_type_dict


def _flavor_get_query(context, session=None, read_deleted=None):
    query = model_query(context, models.InstanceTypes, session=session,
                       read_deleted=read_deleted).\
                       options(joinedload('extra_specs'))
    if not context.is_admin:
        the_filter = [models.InstanceTypes.is_public == true()]
        the_filter.extend([
            models.InstanceTypes.projects.any(project_id=context.project_id)
        ])
        query = query.filter(or_(*the_filter))
    return query


@require_context
def flavor_get_all(context, inactive=False, filters=None,
                   sort_key='flavorid', sort_dir='asc', limit=None,
                   marker=None):
    """Returns all flavors.
    """
    filters = filters or {}

    # FIXME(sirp): now that we have the `disabled` field for flavors, we
    # should probably remove the use of `deleted` to mark inactive. `deleted`
    # should mean truly deleted, e.g. we can safely purge the record out of the
    # database.
    read_deleted = "yes" if inactive else "no"

    query = _flavor_get_query(context, read_deleted=read_deleted)

    if 'min_memory_mb' in filters:
        query = query.filter(
                models.InstanceTypes.memory_mb >= filters['min_memory_mb'])

    if 'min_root_gb' in filters:
        query = query.filter(
                models.InstanceTypes.root_gb >= filters['min_root_gb'])

    if 'disabled' in filters:
        query = query.filter(
                models.InstanceTypes.disabled == filters['disabled'])

    if 'is_public' in filters and filters['is_public'] is not None:
        the_filter = [models.InstanceTypes.is_public == filters['is_public']]
        if filters['is_public'] and context.project_id is not None:
            the_filter.extend([
                models.InstanceTypes.projects.any(
                    project_id=context.project_id, deleted=0)
            ])
        if len(the_filter) > 1:
            query = query.filter(or_(*the_filter))
        else:
            query = query.filter(the_filter[0])

    marker_row = None
    if marker is not None:
        marker_row = _flavor_get_query(context, read_deleted=read_deleted).\
                    filter_by(flavorid=marker).\
                    first()
        if not marker_row:
            raise exception.MarkerNotFound(marker)

    query = sqlalchemyutils.paginate_query(query, models.InstanceTypes, limit,
                                           [sort_key, 'id'],
                                           marker=marker_row,
                                           sort_dir=sort_dir)

    inst_types = query.all()

    return [_dict_with_extra_specs(i) for i in inst_types]


def _flavor_get_id_from_flavor_query(context, flavor_id, session=None):
    return model_query(context, models.InstanceTypes.id, read_deleted="no",
                       session=session, base_model=models.InstanceTypes).\
                filter_by(flavorid=flavor_id)


def _flavor_get_id_from_flavor(context, flavor_id, session=None):
    result = _flavor_get_id_from_flavor_query(context, flavor_id,
                                                     session=session).\
                    first()
    if not result:
        raise exception.FlavorNotFound(flavor_id=flavor_id)
    return result[0]


@require_context
def flavor_get(context, id):
    """Returns a dict describing specific flavor."""
    result = _flavor_get_query(context).\
                        filter_by(id=id).\
                        first()
    if not result:
        raise exception.FlavorNotFound(flavor_id=id)
    return _dict_with_extra_specs(result)


@require_context
def flavor_get_by_name(context, name):
    """Returns a dict describing specific flavor."""
    result = _flavor_get_query(context).\
                        filter_by(name=name).\
                        first()
    if not result:
        raise exception.FlavorNotFoundByName(flavor_name=name)
    return _dict_with_extra_specs(result)


@require_context
def flavor_get_by_flavor_id(context, flavor_id, read_deleted):
    """Returns a dict describing specific flavor_id."""
    result = _flavor_get_query(context, read_deleted=read_deleted).\
                        filter_by(flavorid=flavor_id).\
                        order_by(asc("deleted"), asc("id")).\
                        first()
    if not result:
        raise exception.FlavorNotFound(flavor_id=flavor_id)
    return _dict_with_extra_specs(result)


@require_admin_context
def flavor_destroy(context, name):
    """Marks specific flavor as deleted."""
    session = get_session()
    with session.begin():
        ref = model_query(context, models.InstanceTypes, session=session,
                          read_deleted="no").\
                    filter_by(name=name).\
                    first()
        if not ref:
            raise exception.FlavorNotFoundByName(flavor_name=name)

        ref.soft_delete(session=session)
        model_query(context, models.InstanceTypeExtraSpecs,
                    session=session, read_deleted="no").\
                filter_by(instance_type_id=ref['id']).\
                soft_delete()
        model_query(context, models.InstanceTypeProjects,
                    session=session, read_deleted="no").\
                filter_by(instance_type_id=ref['id']).\
                soft_delete()


def _flavor_access_query(context, session=None):
    return model_query(context, models.InstanceTypeProjects, session=session,
                       read_deleted="no")


@require_admin_context
def flavor_access_get_by_flavor_id(context, flavor_id):
    """Get flavor access list by flavor id."""
    instance_type_id_subq = \
            _flavor_get_id_from_flavor_query(context, flavor_id)
    access_refs = _flavor_access_query(context).\
                        filter_by(instance_type_id=instance_type_id_subq).\
                        all()
    return access_refs


@require_admin_context
def flavor_access_add(context, flavor_id, project_id):
    """Add given tenant to the flavor access list."""
    instance_type_id = _flavor_get_id_from_flavor(context, flavor_id)

    access_ref = models.InstanceTypeProjects()
    access_ref.update({"instance_type_id": instance_type_id,
                       "project_id": project_id})
    try:
        access_ref.save()
    except db_exc.DBDuplicateEntry:
        raise exception.FlavorAccessExists(flavor_id=flavor_id,
                                            project_id=project_id)
    return access_ref


@require_admin_context
def flavor_access_remove(context, flavor_id, project_id):
    """Remove given tenant from the flavor access list."""
    instance_type_id = _flavor_get_id_from_flavor(context, flavor_id)

    count = _flavor_access_query(context).\
                    filter_by(instance_type_id=instance_type_id).\
                    filter_by(project_id=project_id).\
                    soft_delete(synchronize_session=False)
    if count == 0:
        raise exception.FlavorAccessNotFound(flavor_id=flavor_id,
                                             project_id=project_id)


def _flavor_extra_specs_get_query(context, flavor_id, session=None):
    instance_type_id_subq = \
            _flavor_get_id_from_flavor_query(context, flavor_id)

    return model_query(context, models.InstanceTypeExtraSpecs, session=session,
                       read_deleted="no").\
                filter_by(instance_type_id=instance_type_id_subq)


@require_context
def flavor_extra_specs_get(context, flavor_id):
    rows = _flavor_extra_specs_get_query(context, flavor_id).all()
    return dict([(row['key'], row['value']) for row in rows])


@require_context
def flavor_extra_specs_get_item(context, flavor_id, key):
    result = _flavor_extra_specs_get_query(context, flavor_id).\
                filter(models.InstanceTypeExtraSpecs.key == key).\
                first()
    if not result:
        raise exception.FlavorExtraSpecsNotFound(
                extra_specs_key=key, flavor_id=flavor_id)

    return {result["key"]: result["value"]}


@require_context
def flavor_extra_specs_delete(context, flavor_id, key):
    result = _flavor_extra_specs_get_query(context, flavor_id).\
                     filter(models.InstanceTypeExtraSpecs.key == key).\
                     soft_delete(synchronize_session=False)
    # did not find the extra spec
    if result == 0:
        raise exception.FlavorExtraSpecsNotFound(
                extra_specs_key=key, flavor_id=flavor_id)


@require_context
def flavor_extra_specs_update_or_create(context, flavor_id, specs,
                                               max_retries=10):
    for attempt in xrange(max_retries):
        try:
            session = get_session()
            with session.begin():
                instance_type_id = _flavor_get_id_from_flavor(context,
                                                         flavor_id, session)

                spec_refs = model_query(context, models.InstanceTypeExtraSpecs,
                                        session=session, read_deleted="no").\
                  filter_by(instance_type_id=instance_type_id).\
                  filter(models.InstanceTypeExtraSpecs.key.in_(specs.keys())).\
                  all()

                existing_keys = set()
                for spec_ref in spec_refs:
                    key = spec_ref["key"]
                    existing_keys.add(key)
                    spec_ref.update({"value": specs[key]})

                for key, value in specs.iteritems():
                    if key in existing_keys:
                        continue
                    spec_ref = models.InstanceTypeExtraSpecs()
                    spec_ref.update({"key": key, "value": value,
                                     "instance_type_id": instance_type_id})
                    session.add(spec_ref)

            return specs
        except db_exc.DBDuplicateEntry:
            # a concurrent transaction has been committed,
            # try again unless this was the last attempt
            if attempt == max_retries - 1:
                raise exception.FlavorExtraSpecUpdateCreateFailed(
                                    id=flavor_id, retries=max_retries)


####################


@require_admin_context
def cell_create(context, values):
    cell = models.Cell()
    cell.update(values)
    try:
        cell.save()
    except db_exc.DBDuplicateEntry:
        raise exception.CellExists(name=values['name'])
    return cell


def _cell_get_by_name_query(context, cell_name, session=None):
    return model_query(context, models.Cell,
                       session=session).filter_by(name=cell_name)


@require_admin_context
def cell_update(context, cell_name, values):
    session = get_session()
    with session.begin():
        cell_query = _cell_get_by_name_query(context, cell_name,
                                             session=session)
        if not cell_query.update(values):
            raise exception.CellNotFound(cell_name=cell_name)
        cell = cell_query.first()
    return cell


@require_admin_context
def cell_delete(context, cell_name):
    return _cell_get_by_name_query(context, cell_name).soft_delete()


@require_admin_context
def cell_get(context, cell_name):
    result = _cell_get_by_name_query(context, cell_name).first()
    if not result:
        raise exception.CellNotFound(cell_name=cell_name)
    return result


@require_admin_context
def cell_get_all(context):
    return model_query(context, models.Cell, read_deleted="no").all()


########################
# User-provided metadata

def _instance_metadata_get_multi(context, instance_uuids,
                                 session=None, use_slave=False):
    if not instance_uuids:
        return []
    return model_query(context, models.InstanceMetadata,
                       session=session, use_slave=use_slave).\
                    filter(
            models.InstanceMetadata.instance_uuid.in_(instance_uuids))


def _instance_metadata_get_query(context, instance_uuid, session=None):
    return model_query(context, models.InstanceMetadata, session=session,
                       read_deleted="no").\
                    filter_by(instance_uuid=instance_uuid)


@require_context
def instance_metadata_get(context, instance_uuid):
    rows = _instance_metadata_get_query(context, instance_uuid).all()
    return dict((row['key'], row['value']) for row in rows)


@require_context
@_retry_on_deadlock
def instance_metadata_delete(context, instance_uuid, key):
    _instance_metadata_get_query(context, instance_uuid).\
        filter_by(key=key).\
        soft_delete()


@require_context
@_retry_on_deadlock
def instance_metadata_update(context, instance_uuid, metadata, delete):
    all_keys = metadata.keys()
    session = get_session()
    with session.begin(subtransactions=True):
        if delete:
            _instance_metadata_get_query(context, instance_uuid,
                                         session=session).\
                filter(~models.InstanceMetadata.key.in_(all_keys)).\
                soft_delete(synchronize_session=False)

        already_existing_keys = []
        meta_refs = _instance_metadata_get_query(context, instance_uuid,
                                                 session=session).\
            filter(models.InstanceMetadata.key.in_(all_keys)).\
            all()

        for meta_ref in meta_refs:
            already_existing_keys.append(meta_ref.key)
            meta_ref.update({"value": metadata[meta_ref.key]})

        new_keys = set(all_keys) - set(already_existing_keys)
        for key in new_keys:
            meta_ref = models.InstanceMetadata()
            meta_ref.update({"key": key, "value": metadata[key],
                             "instance_uuid": instance_uuid})
            session.add(meta_ref)

        return metadata


#######################
# System-owned metadata


def _instance_system_metadata_get_multi(context, instance_uuids,
                                        session=None, use_slave=False):
    if not instance_uuids:
        return []
    return model_query(context, models.InstanceSystemMetadata,
                       session=session, use_slave=use_slave).\
                    filter(
            models.InstanceSystemMetadata.instance_uuid.in_(instance_uuids))


def _instance_system_metadata_get_query(context, instance_uuid, session=None):
    return model_query(context, models.InstanceSystemMetadata,
                       session=session).\
                    filter_by(instance_uuid=instance_uuid)


@require_context
def instance_system_metadata_get(context, instance_uuid):
    rows = _instance_system_metadata_get_query(context, instance_uuid).all()
    return dict((row['key'], row['value']) for row in rows)


@require_context
def instance_system_metadata_update(context, instance_uuid, metadata, delete):
    all_keys = metadata.keys()
    session = get_session()
    with session.begin(subtransactions=True):
        if delete:
            _instance_system_metadata_get_query(context, instance_uuid,
                                                session=session).\
                filter(~models.InstanceSystemMetadata.key.in_(all_keys)).\
                soft_delete(synchronize_session=False)

        already_existing_keys = []
        meta_refs = _instance_system_metadata_get_query(context, instance_uuid,
                                                        session=session).\
            filter(models.InstanceSystemMetadata.key.in_(all_keys)).\
            all()

        for meta_ref in meta_refs:
            already_existing_keys.append(meta_ref.key)
            meta_ref.update({"value": metadata[meta_ref.key]})

        new_keys = set(all_keys) - set(already_existing_keys)
        for key in new_keys:
            meta_ref = models.InstanceSystemMetadata()
            meta_ref.update({"key": key, "value": metadata[key],
                             "instance_uuid": instance_uuid})
            session.add(meta_ref)

        return metadata


####################


@require_admin_context
def agent_build_create(context, values):
    agent_build_ref = models.AgentBuild()
    agent_build_ref.update(values)
    try:
        agent_build_ref.save()
    except db_exc.DBDuplicateEntry:
        raise exception.AgentBuildExists(hypervisor=values['hypervisor'],
                        os=values['os'], architecture=values['architecture'])
    return agent_build_ref


@require_admin_context
def agent_build_get_by_triple(context, hypervisor, os, architecture):
    return model_query(context, models.AgentBuild, read_deleted="no").\
                   filter_by(hypervisor=hypervisor).\
                   filter_by(os=os).\
                   filter_by(architecture=architecture).\
                   first()


@require_admin_context
def agent_build_get_all(context, hypervisor=None):
    if hypervisor:
        return model_query(context, models.AgentBuild, read_deleted="no").\
                   filter_by(hypervisor=hypervisor).\
                   all()
    else:
        return model_query(context, models.AgentBuild, read_deleted="no").\
                   all()


@require_admin_context
def agent_build_destroy(context, agent_build_id):
    rows_affected = model_query(context, models.AgentBuild).filter_by(
                                        id=agent_build_id).soft_delete()
    if rows_affected == 0:
        raise exception.AgentBuildNotFound(id=agent_build_id)


@require_admin_context
def agent_build_update(context, agent_build_id, values):
    rows_affected = model_query(context, models.AgentBuild).\
                   filter_by(id=agent_build_id).\
                   update(values)
    if rows_affected == 0:
        raise exception.AgentBuildNotFound(id=agent_build_id)


####################

@require_context
def bw_usage_get(context, uuid, start_period, mac, use_slave=False):
    return model_query(context, models.BandwidthUsage, read_deleted="yes",
                       use_slave=use_slave).\
                           filter_by(start_period=start_period).\
                           filter_by(uuid=uuid).\
                           filter_by(mac=mac).\
                           first()


@require_context
def bw_usage_get_by_uuids(context, uuids, start_period, use_slave=False):
    return (
        model_query(context, models.BandwidthUsage, read_deleted="yes",
                    use_slave=use_slave).
        filter(models.BandwidthUsage.uuid.in_(uuids)).
        filter_by(start_period=start_period).
        all()
    )


@require_context
@_retry_on_deadlock
def bw_usage_update(context, uuid, mac, start_period, bw_in, bw_out,
                    last_ctr_in, last_ctr_out, last_refreshed=None):

    session = get_session()

    if last_refreshed is None:
        last_refreshed = timeutils.utcnow()

    # NOTE(comstud): More often than not, we'll be updating records vs
    # creating records.  Optimize accordingly, trying to update existing
    # records.  Fall back to creation when no rows are updated.
    with session.begin():
        values = {'last_refreshed': last_refreshed,
                  'last_ctr_in': last_ctr_in,
                  'last_ctr_out': last_ctr_out,
                  'bw_in': bw_in,
                  'bw_out': bw_out}
        rows = model_query(context, models.BandwidthUsage,
                              session=session, read_deleted="yes").\
                      filter_by(start_period=start_period).\
                      filter_by(uuid=uuid).\
                      filter_by(mac=mac).\
                      update(values, synchronize_session=False)
        if rows:
            return

        bwusage = models.BandwidthUsage()
        bwusage.start_period = start_period
        bwusage.uuid = uuid
        bwusage.mac = mac
        bwusage.last_refreshed = last_refreshed
        bwusage.bw_in = bw_in
        bwusage.bw_out = bw_out
        bwusage.last_ctr_in = last_ctr_in
        bwusage.last_ctr_out = last_ctr_out
        try:
            bwusage.save(session=session)
        except db_exc.DBDuplicateEntry:
            # NOTE(sirp): Possible race if two greenthreads attempt to create
            # the usage entry at the same time. First one wins.
            pass


####################


@require_context
def vol_get_usage_by_time(context, begin):
    """Return volumes usage that have been updated after a specified time."""
    return model_query(context, models.VolumeUsage, read_deleted="yes").\
                   filter(or_(models.VolumeUsage.tot_last_refreshed == null(),
                              models.VolumeUsage.tot_last_refreshed > begin,
                              models.VolumeUsage.curr_last_refreshed == null(),
                              models.VolumeUsage.curr_last_refreshed > begin,
                              )).\
                              all()


@require_context
def vol_usage_update(context, id, rd_req, rd_bytes, wr_req, wr_bytes,
                     instance_id, project_id, user_id, availability_zone,
                     update_totals=False):
    session = get_session()

    refreshed = timeutils.utcnow()

    with session.begin():
        values = {}
        # NOTE(dricco): We will be mostly updating current usage records vs
        # updating total or creating records. Optimize accordingly.
        if not update_totals:
            values = {'curr_last_refreshed': refreshed,
                      'curr_reads': rd_req,
                      'curr_read_bytes': rd_bytes,
                      'curr_writes': wr_req,
                      'curr_write_bytes': wr_bytes,
                      'instance_uuid': instance_id,
                      'project_id': project_id,
                      'user_id': user_id,
                      'availability_zone': availability_zone}
        else:
            values = {'tot_last_refreshed': refreshed,
                      'tot_reads': models.VolumeUsage.tot_reads + rd_req,
                      'tot_read_bytes': models.VolumeUsage.tot_read_bytes +
                                        rd_bytes,
                      'tot_writes': models.VolumeUsage.tot_writes + wr_req,
                      'tot_write_bytes': models.VolumeUsage.tot_write_bytes +
                                         wr_bytes,
                      'curr_reads': 0,
                      'curr_read_bytes': 0,
                      'curr_writes': 0,
                      'curr_write_bytes': 0,
                      'instance_uuid': instance_id,
                      'project_id': project_id,
                      'user_id': user_id,
                      'availability_zone': availability_zone}

        current_usage = model_query(context, models.VolumeUsage,
                            session=session, read_deleted="yes").\
                            filter_by(volume_id=id).\
                            first()
        if current_usage:
            if (rd_req < current_usage['curr_reads'] or
                rd_bytes < current_usage['curr_read_bytes'] or
                wr_req < current_usage['curr_writes'] or
                    wr_bytes < current_usage['curr_write_bytes']):
                LOG.info(_("Volume(%s) has lower stats then what is in "
                           "the database. Instance must have been rebooted "
                           "or crashed. Updating totals.") % id)
                if not update_totals:
                    values['tot_reads'] = (models.VolumeUsage.tot_reads +
                                           current_usage['curr_reads'])
                    values['tot_read_bytes'] = (
                        models.VolumeUsage.tot_read_bytes +
                        current_usage['curr_read_bytes'])
                    values['tot_writes'] = (models.VolumeUsage.tot_writes +
                                            current_usage['curr_writes'])
                    values['tot_write_bytes'] = (
                        models.VolumeUsage.tot_write_bytes +
                        current_usage['curr_write_bytes'])
                else:
                    values['tot_reads'] = (models.VolumeUsage.tot_reads +
                                           current_usage['curr_reads'] +
                                           rd_req)
                    values['tot_read_bytes'] = (
                        models.VolumeUsage.tot_read_bytes +
                        current_usage['curr_read_bytes'] + rd_bytes)
                    values['tot_writes'] = (models.VolumeUsage.tot_writes +
                                            current_usage['curr_writes'] +
                                            wr_req)
                    values['tot_write_bytes'] = (
                        models.VolumeUsage.tot_write_bytes +
                        current_usage['curr_write_bytes'] + wr_bytes)

            current_usage.update(values)
            current_usage.save(session=session)
            session.refresh(current_usage)
            return current_usage

        vol_usage = models.VolumeUsage()
        vol_usage.volume_id = id
        vol_usage.instance_uuid = instance_id
        vol_usage.project_id = project_id
        vol_usage.user_id = user_id
        vol_usage.availability_zone = availability_zone

        if not update_totals:
            vol_usage.curr_last_refreshed = refreshed
            vol_usage.curr_reads = rd_req
            vol_usage.curr_read_bytes = rd_bytes
            vol_usage.curr_writes = wr_req
            vol_usage.curr_write_bytes = wr_bytes
        else:
            vol_usage.tot_last_refreshed = refreshed
            vol_usage.tot_reads = rd_req
            vol_usage.tot_read_bytes = rd_bytes
            vol_usage.tot_writes = wr_req
            vol_usage.tot_write_bytes = wr_bytes

        vol_usage.save(session=session)

        return vol_usage


####################


def s3_image_get(context, image_id):
    """Find local s3 image represented by the provided id."""
    result = model_query(context, models.S3Image, read_deleted="yes").\
                 filter_by(id=image_id).\
                 first()

    if not result:
        raise exception.ImageNotFound(image_id=image_id)

    return result


def s3_image_get_by_uuid(context, image_uuid):
    """Find local s3 image represented by the provided uuid."""
    result = model_query(context, models.S3Image, read_deleted="yes").\
                 filter_by(uuid=image_uuid).\
                 first()

    if not result:
        raise exception.ImageNotFound(image_id=image_uuid)

    return result


def s3_image_create(context, image_uuid):
    """Create local s3 image represented by provided uuid."""
    try:
        s3_image_ref = models.S3Image()
        s3_image_ref.update({'uuid': image_uuid})
        s3_image_ref.save()
    except Exception as e:
        raise db_exc.DBError(e)

    return s3_image_ref


####################


def _aggregate_get_query(context, model_class, id_field=None, id=None,
                         session=None, read_deleted=None):
    columns_to_join = {models.Aggregate: ['_hosts', '_metadata']}

    query = model_query(context, model_class, session=session,
                        read_deleted=read_deleted)

    for c in columns_to_join.get(model_class, []):
        query = query.options(joinedload(c))

    if id and id_field:
        query = query.filter(id_field == id)

    return query


def aggregate_create(context, values, metadata=None):
    session = get_session()
    query = _aggregate_get_query(context,
                                 models.Aggregate,
                                 models.Aggregate.name,
                                 values['name'],
                                 session=session,
                                 read_deleted='no')
    aggregate = query.first()
    if not aggregate:
        aggregate = models.Aggregate()
        aggregate.update(values)
        aggregate.save(session=session)
        # We don't want these to be lazy loaded later.  We know there is
        # nothing here since we just created this aggregate.
        aggregate._hosts = []
        aggregate._metadata = []
    else:
        raise exception.AggregateNameExists(aggregate_name=values['name'])
    if metadata:
        aggregate_metadata_add(context, aggregate.id, metadata)
    return aggregate_get(context, aggregate.id)


def aggregate_get(context, aggregate_id):
    query = _aggregate_get_query(context,
                                 models.Aggregate,
                                 models.Aggregate.id,
                                 aggregate_id)
    aggregate = query.first()

    if not aggregate:
        raise exception.AggregateNotFound(aggregate_id=aggregate_id)

    return aggregate


def aggregate_get_by_host(context, host, key=None):
    """Return rows that match host (mandatory) and metadata key (optional).

    :param host matches host, and is required.
    :param key Matches metadata key, if not None.
    """
    query = model_query(context, models.Aggregate)
    query = query.options(joinedload('_hosts'))
    query = query.options(joinedload('_metadata'))
    query = query.join('_hosts')
    query = query.filter(models.AggregateHost.host == host)

    if key:
        query = query.join("_metadata").filter(
            models.AggregateMetadata.key == key)
    return query.all()


def aggregate_metadata_get_by_host(context, host, key=None):
    query = model_query(context, models.Aggregate)
    query = query.join("_hosts")
    query = query.join("_metadata")
    query = query.filter(models.AggregateHost.host == host)
    query = query.options(contains_eager("_metadata"))

    if key:
        query = query.filter(models.AggregateMetadata.key == key)
    rows = query.all()

    metadata = collections.defaultdict(set)
    for agg in rows:
        for kv in agg._metadata:
            metadata[kv['key']].add(kv['value'])
    return dict(metadata)


def aggregate_metadata_get_by_metadata_key(context, aggregate_id, key):
    query = model_query(context, models.Aggregate)
    query = query.join("_metadata")
    query = query.filter(models.Aggregate.id == aggregate_id)
    query = query.options(contains_eager("_metadata"))
    query = query.filter(models.AggregateMetadata.key == key)
    rows = query.all()

    metadata = collections.defaultdict(set)
    for agg in rows:
        for kv in agg._metadata:
            metadata[kv['key']].add(kv['value'])
    return dict(metadata)


def aggregate_host_get_by_metadata_key(context, key):
    rows = aggregate_get_by_metadata_key(context, key)
    metadata = collections.defaultdict(set)
    for agg in rows:
        for agghost in agg._hosts:
            metadata[agghost.host].add(agg._metadata[0]['value'])
    return dict(metadata)


def aggregate_get_by_metadata_key(context, key):
    """Return rows that match metadata key.

    :param key Matches metadata key.
    """
    query = model_query(context, models.Aggregate)
    query = query.join("_metadata")
    query = query.filter(models.AggregateMetadata.key == key)
    query = query.options(contains_eager("_metadata"))
    query = query.options(joinedload("_hosts"))
    return query.all()


def aggregate_update(context, aggregate_id, values):
    session = get_session()

    if "name" in values:
        aggregate_by_name = (_aggregate_get_query(context,
                                                  models.Aggregate,
                                                  models.Aggregate.name,
                                                  values['name'],
                                                  session=session,
                                                  read_deleted='no').first())
        if aggregate_by_name and aggregate_by_name.id != aggregate_id:
            # there is another aggregate with the new name
            raise exception.AggregateNameExists(aggregate_name=values['name'])

    aggregate = (_aggregate_get_query(context,
                                     models.Aggregate,
                                     models.Aggregate.id,
                                     aggregate_id,
                                     session=session).first())

    set_delete = True
    if aggregate:
        if "availability_zone" in values:
            az = values.pop('availability_zone')
            if 'metadata' not in values:
                values['metadata'] = {'availability_zone': az}
                set_delete = False
            else:
                values['metadata']['availability_zone'] = az
        metadata = values.get('metadata')
        if metadata is not None:
            aggregate_metadata_add(context,
                                   aggregate_id,
                                   values.pop('metadata'),
                                   set_delete=set_delete)

        aggregate.update(values)
        aggregate.save(session=session)
        values['metadata'] = metadata
        return aggregate_get(context, aggregate.id)
    else:
        raise exception.AggregateNotFound(aggregate_id=aggregate_id)


def aggregate_delete(context, aggregate_id):
    session = get_session()
    with session.begin():
        count = _aggregate_get_query(context,
                                     models.Aggregate,
                                     models.Aggregate.id,
                                     aggregate_id,
                                     session=session).\
                    soft_delete()
        if count == 0:
            raise exception.AggregateNotFound(aggregate_id=aggregate_id)

        # Delete Metadata
        model_query(context,
                    models.AggregateMetadata, session=session).\
                    filter_by(aggregate_id=aggregate_id).\
                    soft_delete()


def aggregate_get_all(context):
    return _aggregate_get_query(context, models.Aggregate).all()


def _aggregate_metadata_get_query(context, aggregate_id, session=None,
                                  read_deleted="yes"):
    return model_query(context,
                       models.AggregateMetadata,
                       read_deleted=read_deleted,
                       session=session).\
                filter_by(aggregate_id=aggregate_id)


@require_aggregate_exists
def aggregate_metadata_get(context, aggregate_id):
    rows = model_query(context,
                       models.AggregateMetadata).\
                       filter_by(aggregate_id=aggregate_id).all()

    return dict([(r['key'], r['value']) for r in rows])


@require_aggregate_exists
def aggregate_metadata_delete(context, aggregate_id, key):
    count = _aggregate_get_query(context,
                                 models.AggregateMetadata,
                                 models.AggregateMetadata.aggregate_id,
                                 aggregate_id).\
                                 filter_by(key=key).\
                                 soft_delete()
    if count == 0:
        raise exception.AggregateMetadataNotFound(aggregate_id=aggregate_id,
                                                  metadata_key=key)


@require_aggregate_exists
def aggregate_metadata_add(context, aggregate_id, metadata, set_delete=False,
                           max_retries=10):
    all_keys = metadata.keys()
    for attempt in xrange(max_retries):
        try:
            session = get_session()
            with session.begin():
                query = _aggregate_metadata_get_query(context, aggregate_id,
                                                      read_deleted='no',
                                                      session=session)
                if set_delete:
                    query.filter(~models.AggregateMetadata.key.in_(all_keys)).\
                        soft_delete(synchronize_session=False)

                query = \
                    query.filter(models.AggregateMetadata.key.in_(all_keys))
                already_existing_keys = set()
                for meta_ref in query.all():
                    key = meta_ref.key
                    meta_ref.update({"value": metadata[key]})
                    already_existing_keys.add(key)

                new_entries = []
                for key, value in metadata.iteritems():
                    if key in already_existing_keys:
                        continue
                    new_entries.append({"key": key,
                                        "value": value,
                                        "aggregate_id": aggregate_id})
                if new_entries:
                    session.execute(
                        models.AggregateMetadata.__table__.insert(),
                        new_entries)

            return metadata
        except db_exc.DBDuplicateEntry:
            # a concurrent transaction has been committed,
            # try again unless this was the last attempt
            with excutils.save_and_reraise_exception() as ctxt:
                if attempt < max_retries - 1:
                    ctxt.reraise = False
                else:
                    msg = _("Add metadata failed for aggregate %(id)s after "
                            "%(retries)s retries") % {"id": aggregate_id,
                                                      "retries": max_retries}
                    LOG.warn(msg)


@require_aggregate_exists
def aggregate_host_get_all(context, aggregate_id):
    rows = model_query(context,
                       models.AggregateHost).\
                       filter_by(aggregate_id=aggregate_id).all()

    return [r.host for r in rows]


@require_aggregate_exists
def aggregate_host_delete(context, aggregate_id, host):
    count = _aggregate_get_query(context,
                                 models.AggregateHost,
                                 models.AggregateHost.aggregate_id,
                                 aggregate_id).\
            filter_by(host=host).\
            soft_delete()
    if count == 0:
        raise exception.AggregateHostNotFound(aggregate_id=aggregate_id,
                                              host=host)


@require_aggregate_exists
def aggregate_host_add(context, aggregate_id, host):
    host_ref = models.AggregateHost()
    host_ref.update({"host": host, "aggregate_id": aggregate_id})
    try:
        host_ref.save()
    except db_exc.DBDuplicateEntry:
        raise exception.AggregateHostExists(host=host,
                                            aggregate_id=aggregate_id)
    return host_ref


################


def instance_fault_create(context, values):
    """Create a new InstanceFault."""
    fault_ref = models.InstanceFault()
    fault_ref.update(values)
    fault_ref.save()
    return dict(fault_ref.iteritems())


def instance_fault_get_by_instance_uuids(context, instance_uuids):
    """Get all instance faults for the provided instance_uuids."""
    if not instance_uuids:
        return {}

    rows = model_query(context, models.InstanceFault, read_deleted='no').\
                       filter(models.InstanceFault.instance_uuid.in_(
                           instance_uuids)).\
                       order_by(desc("created_at"), desc("id")).\
                       all()

    output = {}
    for instance_uuid in instance_uuids:
        output[instance_uuid] = []

    for row in rows:
        data = dict(row.iteritems())
        output[row['instance_uuid']].append(data)

    return output


##################


def action_start(context, values):
    convert_objects_related_datetimes(values, 'start_time')
    action_ref = models.InstanceAction()
    action_ref.update(values)
    action_ref.save()
    return action_ref


def action_finish(context, values):
    convert_objects_related_datetimes(values, 'start_time', 'finish_time')
    session = get_session()
    with session.begin():
        action_ref = model_query(context, models.InstanceAction,
                                 session=session).\
                           filter_by(instance_uuid=values['instance_uuid']).\
                           filter_by(request_id=values['request_id']).\
                           first()

        if not action_ref:
            raise exception.InstanceActionNotFound(
                                        request_id=values['request_id'],
                                        instance_uuid=values['instance_uuid'])

        action_ref.update(values)
    return action_ref


def actions_get(context, instance_uuid):
    """Get all instance actions for the provided uuid."""
    actions = model_query(context, models.InstanceAction).\
                          filter_by(instance_uuid=instance_uuid).\
                          order_by(desc("created_at"), desc("id")).\
                          all()
    return actions


def action_get_by_request_id(context, instance_uuid, request_id):
    """Get the action by request_id and given instance."""
    action = _action_get_by_request_id(context, instance_uuid, request_id)
    return action


def _action_get_by_request_id(context, instance_uuid, request_id,
                                                                session=None):
    result = model_query(context, models.InstanceAction, session=session).\
                         filter_by(instance_uuid=instance_uuid).\
                         filter_by(request_id=request_id).\
                         first()
    return result


def action_event_start(context, values):
    """Start an event on an instance action."""
    convert_objects_related_datetimes(values, 'start_time')
    session = get_session()
    with session.begin():
        action = _action_get_by_request_id(context, values['instance_uuid'],
                                           values['request_id'], session)

        if not action:
            raise exception.InstanceActionNotFound(
                                        request_id=values['request_id'],
                                        instance_uuid=values['instance_uuid'])

        values['action_id'] = action['id']

        event_ref = models.InstanceActionEvent()
        event_ref.update(values)
        session.add(event_ref)
    return event_ref


def action_event_finish(context, values):
    """Finish an event on an instance action."""
    convert_objects_related_datetimes(values, 'start_time', 'finish_time')
    session = get_session()
    with session.begin():
        action = _action_get_by_request_id(context, values['instance_uuid'],
                                           values['request_id'], session)

        if not action:
            raise exception.InstanceActionNotFound(
                                        request_id=values['request_id'],
                                        instance_uuid=values['instance_uuid'])

        event_ref = model_query(context, models.InstanceActionEvent,
                                session=session).\
                            filter_by(action_id=action['id']).\
                            filter_by(event=values['event']).\
                            first()

        if not event_ref:
            raise exception.InstanceActionEventNotFound(action_id=action['id'],
                                                        event=values['event'])
        event_ref.update(values)

        if values['result'].lower() == 'error':
            action.update({'message': 'Error'})

    return event_ref


def action_events_get(context, action_id):
    events = model_query(context, models.InstanceActionEvent).\
                         filter_by(action_id=action_id).\
                         order_by(desc("created_at"), desc("id")).\
                         all()

    return events


def action_event_get_by_id(context, action_id, event_id):
    event = model_query(context, models.InstanceActionEvent).\
                        filter_by(action_id=action_id).\
                        filter_by(id=event_id).\
                        first()

    return event


##################


@require_context
def ec2_instance_create(context, instance_uuid, id=None):
    """Create ec2 compatible instance by provided uuid."""
    ec2_instance_ref = models.InstanceIdMapping()
    ec2_instance_ref.update({'uuid': instance_uuid})
    if id is not None:
        ec2_instance_ref.update({'id': id})

    ec2_instance_ref.save()

    return ec2_instance_ref


@require_context
def ec2_instance_get_by_uuid(context, instance_uuid):
    result = _ec2_instance_get_query(context).\
                    filter_by(uuid=instance_uuid).\
                    first()

    if not result:
        raise exception.InstanceNotFound(instance_id=instance_uuid)

    return result


@require_context
def get_ec2_instance_id_by_uuid(context, instance_id):
    result = ec2_instance_get_by_uuid(context, instance_id)
    return result['id']


@require_context
def ec2_instance_get_by_id(context, instance_id):
    result = _ec2_instance_get_query(context).\
                    filter_by(id=instance_id).\
                    first()

    if not result:
        raise exception.InstanceNotFound(instance_id=instance_id)

    return result


@require_context
def get_instance_uuid_by_ec2_id(context, ec2_id):
    result = ec2_instance_get_by_id(context, ec2_id)
    return result['uuid']


def _ec2_instance_get_query(context, session=None):
    return model_query(context,
                       models.InstanceIdMapping,
                       session=session,
                       read_deleted='yes')


def _task_log_get_query(context, task_name, period_beginning,
                        period_ending, host=None, state=None, session=None):
    query = model_query(context, models.TaskLog, session=session).\
                     filter_by(task_name=task_name).\
                     filter_by(period_beginning=period_beginning).\
                     filter_by(period_ending=period_ending)
    if host is not None:
        query = query.filter_by(host=host)
    if state is not None:
        query = query.filter_by(state=state)
    return query


@require_admin_context
def task_log_get(context, task_name, period_beginning, period_ending, host,
                 state=None):
    return _task_log_get_query(context, task_name, period_beginning,
                               period_ending, host, state).first()


@require_admin_context
def task_log_get_all(context, task_name, period_beginning, period_ending,
                     host=None, state=None):
    return _task_log_get_query(context, task_name, period_beginning,
                               period_ending, host, state).all()


@require_admin_context
def task_log_begin_task(context, task_name, period_beginning, period_ending,
                        host, task_items=None, message=None):

    task = models.TaskLog()
    task.task_name = task_name
    task.period_beginning = period_beginning
    task.period_ending = period_ending
    task.host = host
    task.state = "RUNNING"
    if message:
        task.message = message
    if task_items:
        task.task_items = task_items
    try:
        task.save()
    except db_exc.DBDuplicateEntry:
        raise exception.TaskAlreadyRunning(task_name=task_name, host=host)


@require_admin_context
def task_log_end_task(context, task_name, period_beginning, period_ending,
                      host, errors, message=None):
    values = dict(state="DONE", errors=errors)
    if message:
        values["message"] = message

    session = get_session()
    with session.begin():
        rows = _task_log_get_query(context, task_name, period_beginning,
                                       period_ending, host, session=session).\
                        update(values)
        if rows == 0:
            # It's not running!
            raise exception.TaskNotRunning(task_name=task_name, host=host)


def _get_default_deleted_value(table):
    # TODO(dripton): It would be better to introspect the actual default value
    # from the column, but I don't see a way to do that in the low-level APIs
    # of SQLAlchemy 0.7.  0.8 has better introspection APIs, which we should
    # use when Nova is ready to require 0.8.

    # NOTE(mikal): this is a little confusing. This method returns the value
    # that a _not_deleted_ row would have.
    deleted_column_type = table.c.deleted.type
    if isinstance(deleted_column_type, Integer):
        return 0
    elif isinstance(deleted_column_type, Boolean):
        return False
    elif isinstance(deleted_column_type, String):
        return ""
    else:
        return None


@require_admin_context
def archive_deleted_rows_for_table(context, tablename, max_rows):
    """Move up to max_rows rows from one tables to the corresponding
    shadow table. The context argument is only used for the decorator.

    :returns: number of rows archived
    """
    # NOTE(guochbo): There is a circular import, nova.db.sqlalchemy.utils
    # imports nova.db.sqlalchemy.api.
    from nova.db.sqlalchemy import utils as db_utils

    engine = get_engine()
    conn = engine.connect()
    metadata = MetaData()
    metadata.bind = engine
    table = Table(tablename, metadata, autoload=True)
    default_deleted_value = _get_default_deleted_value(table)
    shadow_tablename = _SHADOW_TABLE_PREFIX + tablename
    rows_archived = 0
    try:
        shadow_table = Table(shadow_tablename, metadata, autoload=True)
    except NoSuchTableError:
        # No corresponding shadow table; skip it.
        return rows_archived

    if tablename == "dns_domains":
        # We have one table (dns_domains) where the key is called
        # "domain" rather than "id"
        column = table.c.domain
    else:
        column = table.c.id
    # NOTE(guochbo): Use InsertFromSelect and DeleteFromSelect to avoid
    # database's limit of maximum parameter in one SQL statement.
    query_insert = sql.select([table],
                          table.c.deleted != default_deleted_value).\
                          order_by(column).limit(max_rows)
    query_delete = sql.select([column],
                          table.c.deleted != default_deleted_value).\
                          order_by(column).limit(max_rows)

    insert_statement = sqlalchemyutils.InsertFromSelect(
        shadow_table, query_insert)
    delete_statement = db_utils.DeleteFromSelect(table, query_delete, column)
    try:
        # Group the insert and delete in a transaction.
        with conn.begin():
            conn.execute(insert_statement)
            result_delete = conn.execute(delete_statement)
    except db_exc.DBError:
        # TODO(ekudryashova): replace by DBReferenceError when db layer
        # raise it.
        # A foreign key constraint keeps us from deleting some of
        # these rows until we clean up a dependent table.  Just
        # skip this table for now; we'll come back to it later.
        msg = _("IntegrityError detected when archiving table %s") % tablename
        LOG.warn(msg)
        return rows_archived

    rows_archived = result_delete.rowcount

    return rows_archived


@require_admin_context
def archive_deleted_rows(context, max_rows=None):
    """Move up to max_rows rows from production tables to the corresponding
    shadow tables.

    :returns: Number of rows archived.
    """
    # The context argument is only used for the decorator.
    tablenames = []
    for model_class in models.__dict__.itervalues():
        if hasattr(model_class, "__tablename__"):
            tablenames.append(model_class.__tablename__)
    rows_archived = 0
    for tablename in tablenames:
        rows_archived += archive_deleted_rows_for_table(context, tablename,
                                         max_rows=max_rows - rows_archived)
        if rows_archived >= max_rows:
            break
    return rows_archived


####################


def _instance_group_get_query(context, model_class, id_field=None, id=None,
                              session=None, read_deleted=None):
    columns_to_join = {models.InstanceGroup: ['_policies', '_members']}
    query = model_query(context, model_class, session=session,
                        read_deleted=read_deleted)

    for c in columns_to_join.get(model_class, []):
        query = query.options(joinedload(c))

    if id and id_field:
        query = query.filter(id_field == id)

    return query


def instance_group_create(context, values, policies=None,
                          members=None):
    """Create a new group."""
    uuid = values.get('uuid', None)
    if uuid is None:
        uuid = uuidutils.generate_uuid()
        values['uuid'] = uuid
    session = get_session()
    with session.begin():
        try:
            group = models.InstanceGroup()
            group.update(values)
            group.save(session=session)
        except db_exc.DBDuplicateEntry:
            raise exception.InstanceGroupIdExists(group_uuid=uuid)

        # We don't want these to be lazy loaded later. We know there is
        # nothing here since we just created this instance group.
        group._policies = []
        group._members = []
        if policies:
            _instance_group_policies_add(context, group.id, policies,
                                         session=session)
        if members:
            _instance_group_members_add(context, group.id, members,
                                        session=session)
    return instance_group_get(context, uuid)


def instance_group_get(context, group_uuid):
    """Get a specific group by uuid."""
    group = _instance_group_get_query(context,
                                      models.InstanceGroup,
                                      models.InstanceGroup.uuid,
                                      group_uuid).\
                            first()
    if not group:
        raise exception.InstanceGroupNotFound(group_uuid=group_uuid)
    return group


def instance_group_update(context, group_uuid, values):
    """Update the attributes of an group.

    If values contains a metadata key, it updates the aggregate metadata
    too. Similarly for the policies and members.
    """
    session = get_session()
    with session.begin():
        group = model_query(context,
                            models.InstanceGroup,
                            session=session).\
                filter_by(uuid=group_uuid).\
                first()
        if not group:
            raise exception.InstanceGroupNotFound(group_uuid=group_uuid)

        policies = values.get('policies')
        if policies is not None:
            _instance_group_policies_add(context,
                                         group.id,
                                         values.pop('policies'),
                                         set_delete=True,
                                         session=session)
        members = values.get('members')
        if members is not None:
            _instance_group_members_add(context,
                                        group.id,
                                        values.pop('members'),
                                        set_delete=True,
                                        session=session)

        group.update(values)

        if policies:
            values['policies'] = policies
        if members:
            values['members'] = members


def instance_group_delete(context, group_uuid):
    """Delete an group."""
    session = get_session()
    with session.begin():
        group_id = _instance_group_id(context, group_uuid, session=session)

        count = _instance_group_get_query(context,
                                          models.InstanceGroup,
                                          models.InstanceGroup.uuid,
                                          group_uuid,
                                          session=session).soft_delete()
        if count == 0:
            raise exception.InstanceGroupNotFound(group_uuid=group_uuid)

        # Delete policies, metadata and members
        instance_models = [models.InstanceGroupPolicy,
                           models.InstanceGroupMember]
        for model in instance_models:
            model_query(context, model, session=session).\
                    filter_by(group_id=group_id).\
                    soft_delete()


def instance_group_get_all(context):
    """Get all groups."""
    return _instance_group_get_query(context, models.InstanceGroup).all()


def instance_group_get_all_by_project_id(context, project_id):
    """Get all groups."""
    return _instance_group_get_query(context, models.InstanceGroup).\
                            filter_by(project_id=project_id).\
                            all()


def _instance_group_count_by_project_and_user(context, project_id,
                                              user_id, session=None):
    return model_query(context, models.InstanceGroup, read_deleted="no",
                       session=session).\
                   filter_by(project_id=project_id).\
                   filter_by(user_id=user_id).\
                   count()


def _instance_group_model_get_query(context, model_class, group_id,
                                    session=None, read_deleted='no'):
    return model_query(context,
                       model_class,
                       read_deleted=read_deleted,
                       session=session).\
                filter_by(group_id=group_id)


def _instance_group_id(context, group_uuid, session=None):
    """Returns the group database ID for the group UUID."""

    result = model_query(context,
                         models.InstanceGroup.id,
                         base_model=models.InstanceGroup,
                         session=session).\
                filter_by(uuid=group_uuid).\
                first()
    if not result:
        raise exception.InstanceGroupNotFound(group_uuid=group_uuid)
    return result.id


def _instance_group_members_add(context, id, members, set_delete=False,
                                session=None):
    if not session:
        session = get_session()

    all_members = set(members)
    with session.begin(subtransactions=True):
        query = _instance_group_model_get_query(context,
                                                models.InstanceGroupMember,
                                                id,
                                                session=session)
        if set_delete:
            query.filter(~models.InstanceGroupMember.instance_id.in_(
                         all_members)).\
                  soft_delete(synchronize_session=False)

        query = query.filter(
                models.InstanceGroupMember.instance_id.in_(all_members))
        already_existing = set()
        for member_ref in query.all():
            already_existing.add(member_ref.instance_id)

        for instance_id in members:
            if instance_id in already_existing:
                continue
            member_ref = models.InstanceGroupMember()
            member_ref.update({'instance_id': instance_id,
                               'group_id': id})
            session.add(member_ref)

        return members


def instance_group_members_add(context, group_uuid, members,
                               set_delete=False):
    id = _instance_group_id(context, group_uuid)
    return _instance_group_members_add(context, id, members,
                                       set_delete=set_delete)


def instance_group_member_delete(context, group_uuid, instance_id):
    id = _instance_group_id(context, group_uuid)
    count = _instance_group_get_query(context,
                                      models.InstanceGroupMember,
                                      models.InstanceGroupMember.group_id,
                                      id).\
                            filter_by(instance_id=instance_id).\
                            soft_delete()
    if count == 0:
        raise exception.InstanceGroupMemberNotFound(group_uuid=group_uuid,
                                                    instance_id=instance_id)


def instance_group_members_get(context, group_uuid):
    id = _instance_group_id(context, group_uuid)
    instances = model_query(context,
                            models.InstanceGroupMember.instance_id,
                            base_model=models.InstanceGroupMember).\
                    filter_by(group_id=id).all()
    return [instance[0] for instance in instances]


def _instance_group_policies_add(context, id, policies, set_delete=False,
                                 session=None):
    if not session:
        session = get_session()

    allpols = set(policies)
    with session.begin(subtransactions=True):
        query = _instance_group_model_get_query(context,
                                                models.InstanceGroupPolicy,
                                                id,
                                                session=session)
        if set_delete:
            query.filter(~models.InstanceGroupPolicy.policy.in_(allpols)).\
                soft_delete(synchronize_session=False)

        query = query.filter(models.InstanceGroupPolicy.policy.in_(allpols))
        already_existing = set()
        for policy_ref in query.all():
            already_existing.add(policy_ref.policy)

        for policy in policies:
            if policy in already_existing:
                continue
            policy_ref = models.InstanceGroupPolicy()
            policy_ref.update({'policy': policy,
                               'group_id': id})
            session.add(policy_ref)

        return policies


def instance_group_policies_add(context, group_uuid, policies,
                                set_delete=False):
    id = _instance_group_id(context, group_uuid)
    return _instance_group_policies_add(context, id, policies,
                                        set_delete=set_delete)


def instance_group_policy_delete(context, group_uuid, policy):
    id = _instance_group_id(context, group_uuid)
    count = _instance_group_get_query(context,
                                      models.InstanceGroupPolicy,
                                      models.InstanceGroupPolicy.group_id,
                                      id).\
                            filter_by(policy=policy).\
                            soft_delete()
    if count == 0:
        raise exception.InstanceGroupPolicyNotFound(group_uuid=group_uuid,
                                                    policy=policy)


def instance_group_policies_get(context, group_uuid):
    id = _instance_group_id(context, group_uuid)
    policies = model_query(context,
                           models.InstanceGroupPolicy.policy,
                           base_model=models.InstanceGroupPolicy).\
                    filter_by(group_id=id).all()
    return [policy[0] for policy in policies]


####################


@require_admin_context
def pci_device_get_by_addr(context, node_id, dev_addr):
    pci_dev_ref = model_query(context, models.PciDevice).\
                        filter_by(compute_node_id=node_id).\
                        filter_by(address=dev_addr).\
                        first()
    if not pci_dev_ref:
        raise exception.PciDeviceNotFound(node_id=node_id, address=dev_addr)
    return pci_dev_ref


@require_admin_context
def pci_device_get_by_id(context, id):
    pci_dev_ref = model_query(context, models.PciDevice).\
                        filter_by(id=id).\
                        first()
    if not pci_dev_ref:
        raise exception.PciDeviceNotFoundById(id=id)
    return pci_dev_ref


@require_admin_context
def pci_device_get_all_by_node(context, node_id):
    return model_query(context, models.PciDevice).\
                       filter_by(compute_node_id=node_id).\
                       all()


@require_context
def pci_device_get_all_by_instance_uuid(context, instance_uuid):
    return model_query(context, models.PciDevice).\
                       filter_by(status='allocated').\
                       filter_by(instance_uuid=instance_uuid).\
                       all()


def _instance_pcidevs_get_multi(context, instance_uuids, session=None):
    return model_query(context, models.PciDevice, session=session).\
        filter_by(status='allocated').\
        filter(models.PciDevice.instance_uuid.in_(instance_uuids))


@require_admin_context
def pci_device_destroy(context, node_id, address):
    result = model_query(context, models.PciDevice).\
                         filter_by(compute_node_id=node_id).\
                         filter_by(address=address).\
                         soft_delete()
    if not result:
        raise exception.PciDeviceNotFound(node_id=node_id, address=address)


@require_admin_context
def pci_device_update(context, node_id, address, values):
    session = get_session()
    with session.begin():
        device = model_query(context, models.PciDevice, session=session,
                             read_deleted="no").\
                        filter_by(compute_node_id=node_id).\
                        filter_by(address=address).\
                        first()
        if not device:
            device = models.PciDevice()
        device.update(values)
        session.add(device)
    return device
