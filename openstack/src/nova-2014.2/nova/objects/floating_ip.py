#    Copyright 2014 Red Hat, Inc.
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

from nova import db
from nova import exception
from nova import objects
from nova.objects import base as obj_base
from nova.objects import fields
from nova import utils

FLOATING_IP_OPTIONAL_ATTRS = ['fixed_ip']


class FloatingIP(obj_base.NovaPersistentObject, obj_base.NovaObject):
    # Version 1.0: Initial version
    # Version 1.1: Added _get_addresses_by_instance_uuid()
    # Version 1.2: FixedIP <= version 1.2
    # Version 1.3: FixedIP <= version 1.3
    # Version 1.4: FixedIP <= version 1.4
    VERSION = '1.4'
    fields = {
        'id': fields.IntegerField(),
        'address': fields.IPAddressField(),
        'fixed_ip_id': fields.IntegerField(nullable=True),
        'project_id': fields.UUIDField(nullable=True),
        'host': fields.StringField(nullable=True),
        'auto_assigned': fields.BooleanField(),
        'pool': fields.StringField(nullable=True),
        'interface': fields.StringField(nullable=True),
        'fixed_ip': fields.ObjectField('FixedIP', nullable=True),
        }

    def obj_make_compatible(self, primitive, target_version):
        target_version = utils.convert_version_to_tuple(target_version)
        if target_version < (1, 2) and 'fixed_ip' in primitive:
            self.fixed_ip.obj_make_compatible(
                    primitive['fixed_ip']['nova_object.data'], '1.1')
            primitive['fixed_ip']['nova_object.version'] = '1.1'
        elif target_version < (1, 3) and self.obj_attr_is_set('fixed_ip'):
            self.fixed_ip.obj_make_compatible(
                    primitive['fixed_ip']['nova_object.data'], '1.2')
            primitive['fixed_ip']['nova_object.version'] = '1.2'
        elif target_version < (1, 4) and self.obj_attr_is_set('fixed_ip'):
            self.fixed_ip.obj_make_compatible(
                    primitive['fixed_ip']['nova_object.data'], '1.3')
            primitive['fixed_ip']['nova_object.version'] = '1.3'

    @staticmethod
    def _from_db_object(context, floatingip, db_floatingip,
                        expected_attrs=None):
        if expected_attrs is None:
            expected_attrs = []
        for field in floatingip.fields:
            if field not in FLOATING_IP_OPTIONAL_ATTRS:
                floatingip[field] = db_floatingip[field]
        if ('fixed_ip' in expected_attrs and
                db_floatingip['fixed_ip'] is not None):
            floatingip.fixed_ip = objects.FixedIP._from_db_object(
                context, objects.FixedIP(context), db_floatingip['fixed_ip'])
        floatingip._context = context
        floatingip.obj_reset_changes()
        return floatingip

    def obj_load_attr(self, attrname):
        if attrname not in FLOATING_IP_OPTIONAL_ATTRS:
            raise exception.ObjectActionError(
                action='obj_load_attr',
                reason='attribute %s is not lazy-loadable' % attrname)
        if not self._context:
            raise exception.OrphanedObjectError(method='obj_load_attr',
                                                objtype=self.obj_name())
        if self.fixed_ip_id is not None:
            self.fixed_ip = objects.FixedIP.get_by_id(
                self._context, self.fixed_ip_id, expected_attrs=['network'])
        else:
            self.fixed_ip = None

    @obj_base.remotable_classmethod
    def get_by_id(cls, context, id):
        db_floatingip = db.floating_ip_get(context, id)
        # XXX joins fixed.instance
        return cls._from_db_object(context, cls(context), db_floatingip,
                                   expected_attrs=['fixed_ip'])

    @obj_base.remotable_classmethod
    def get_by_address(cls, context, address):
        db_floatingip = db.floating_ip_get_by_address(context, str(address))
        return cls._from_db_object(context, cls(context), db_floatingip)

    @obj_base.remotable_classmethod
    def get_pool_names(cls, context):
        return [x['name'] for x in db.floating_ip_get_pools(context)]

    @obj_base.remotable_classmethod
    def allocate_address(cls, context, project_id, pool, auto_assigned=False):
        return db.floating_ip_allocate_address(context, project_id, pool,
                                               auto_assigned=auto_assigned)

    @obj_base.remotable_classmethod
    def associate(cls, context, floating_address, fixed_address, host):
        db_fixed = db.floating_ip_fixed_ip_associate(context,
                                                     str(floating_address),
                                                     str(fixed_address),
                                                     host)
        if db_fixed is None:
            return None

        floating = FloatingIP(
            context=context, address=floating_address, host=host,
            fixed_ip_id=db_fixed['id'],
            fixed_ip=objects.FixedIP._from_db_object(
                context, objects.FixedIP(context), db_fixed,
                expected_attrs=['network']))
        return floating

    @obj_base.remotable_classmethod
    def deallocate(cls, context, address):
        return db.floating_ip_deallocate(context, str(address))

    @obj_base.remotable_classmethod
    def destroy(cls, context, address):
        db.floating_ip_destroy(context, str(address))

    @obj_base.remotable_classmethod
    def disassociate(cls, context, address):
        db_fixed = db.floating_ip_disassociate(context, str(address))

        return cls(context=context, address=address,
                   fixed_ip_id=db_fixed['id'],
                   fixed_ip=objects.FixedIP._from_db_object(
                       context, objects.FixedIP(context), db_fixed,
                       expected_attrs=['network']))

    @obj_base.remotable_classmethod
    def _get_addresses_by_instance_uuid(cls, context, instance_uuid):
        return db.instance_floating_address_get_all(context, instance_uuid)

    @classmethod
    def get_addresses_by_instance(cls, context, instance):
        return cls._get_addresses_by_instance_uuid(context, instance['uuid'])

    @obj_base.remotable
    def save(self, context):
        updates = self.obj_get_changes()
        if 'address' in updates:
            raise exception.ObjectActionError(action='save',
                                              reason='address is not mutable')
        if 'fixed_ip_id' in updates:
            reason = 'fixed_ip_id is not mutable'
            raise exception.ObjectActionError(action='save', reason=reason)

        # NOTE(danms): Make sure we don't pass the calculated fixed_ip
        # relationship to the DB update method
        updates.pop('fixed_ip', None)

        db_floatingip = db.floating_ip_update(context, str(self.address),
                                              updates)
        self._from_db_object(context, self, db_floatingip)


class FloatingIPList(obj_base.ObjectListBase, obj_base.NovaObject):
    # Version 1.3: FloatingIP 1.2
    # Version 1.4: FloatingIP 1.3
    # Version 1.5: FloatingIP 1.4
    fields = {
        'objects': fields.ListOfObjectsField('FloatingIP'),
        }
    child_versions = {
        '1.0': '1.0',
        '1.1': '1.1',
        '1.2': '1.1',
        '1.3': '1.2',
        '1.4': '1.3',
        '1.5': '1.4',
        }
    VERSION = '1.5'

    @obj_base.remotable_classmethod
    def get_all(cls, context):
        db_floatingips = db.floating_ip_get_all(context)
        return obj_base.obj_make_list(context, cls(context),
                                      objects.FloatingIP, db_floatingips)

    @obj_base.remotable_classmethod
    def get_by_host(cls, context, host):
        db_floatingips = db.floating_ip_get_all_by_host(context, host)
        return obj_base.obj_make_list(context, cls(context),
                                      objects.FloatingIP, db_floatingips)

    @obj_base.remotable_classmethod
    def get_by_project(cls, context, project_id):
        db_floatingips = db.floating_ip_get_all_by_project(context, project_id)
        return obj_base.obj_make_list(context, cls(context),
                                      objects.FloatingIP, db_floatingips)

    @obj_base.remotable_classmethod
    def get_by_fixed_address(cls, context, fixed_address):
        db_floatingips = db.floating_ip_get_by_fixed_address(
            context, str(fixed_address))
        return obj_base.obj_make_list(context, cls(context),
                                      objects.FloatingIP, db_floatingips)

    @obj_base.remotable_classmethod
    def get_by_fixed_ip_id(cls, context, fixed_ip_id):
        db_floatingips = db.floating_ip_get_by_fixed_ip_id(context,
                                                           fixed_ip_id)
        return obj_base.obj_make_list(context, cls(), FloatingIP,
                                      db_floatingips)

    @staticmethod
    def make_ip_info(address, pool, interface):
        return {'address': str(address),
                'pool': pool,
                'interface': interface}

    @obj_base.remotable_classmethod
    def create(cls, context, ip_info, want_result=False):
        db_floatingips = db.floating_ip_bulk_create(context, ip_info)
        if want_result:
            return obj_base.obj_make_list(context, cls(), FloatingIP,
                                          db_floatingips)

    @obj_base.remotable_classmethod
    def destroy(cls, context, ips):
        db.floating_ip_bulk_destroy(context, ips)
