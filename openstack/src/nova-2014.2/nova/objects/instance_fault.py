#    Copyright 2013 IBM Corp.
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

import itertools

from nova.cells import opts as cells_opts
from nova.cells import rpcapi as cells_rpcapi
from nova import db
from nova import exception
from nova.i18n import _LE
from nova import objects
from nova.objects import base
from nova.objects import fields
from nova.openstack.common import log as logging


LOG = logging.getLogger(__name__)


class InstanceFault(base.NovaPersistentObject, base.NovaObject):
    # Version 1.0: Initial version
    # Version 1.1: String attributes updated to support unicode
    # Version 1.2: Added create()
    VERSION = '1.2'

    fields = {
        'id': fields.IntegerField(),
        'instance_uuid': fields.UUIDField(),
        'code': fields.IntegerField(),
        'message': fields.StringField(nullable=True),
        'details': fields.StringField(nullable=True),
        'host': fields.StringField(nullable=True),
        }

    @staticmethod
    def _from_db_object(context, fault, db_fault):
        # NOTE(danms): These are identical right now
        for key in fault.fields:
            fault[key] = db_fault[key]
        fault._context = context
        fault.obj_reset_changes()
        return fault

    @base.remotable_classmethod
    def get_latest_for_instance(cls, context, instance_uuid):
        db_faults = db.instance_fault_get_by_instance_uuids(context,
                                                            [instance_uuid])
        if instance_uuid in db_faults and db_faults[instance_uuid]:
            return cls._from_db_object(context, cls(),
                                       db_faults[instance_uuid][0])

    @base.remotable
    def create(self, context):
        if self.obj_attr_is_set('id'):
            raise exception.ObjectActionError(action='create',
                                              reason='already created')
        values = {
            'instance_uuid': self.instance_uuid,
            'code': self.code,
            'message': self.message,
            'details': self.details,
            'host': self.host,
            }
        db_fault = db.instance_fault_create(context, values)
        self._from_db_object(context, self, db_fault)
        self.obj_reset_changes()
        # Cells should only try sending a message over to nova-cells
        # if cells is enabled and we're not the API cell. Otherwise,
        # if the API cell is calling this, we could end up with
        # infinite recursion.
        if cells_opts.get_cell_type() == 'compute':
            try:
                cells_rpcapi.CellsAPI().instance_fault_create_at_top(
                    context, db_fault)
            except Exception:
                LOG.exception(_LE("Failed to notify cells of instance fault"))


class InstanceFaultList(base.ObjectListBase, base.NovaObject):
    # Version 1.0: Initial version
    #              InstanceFault <= version 1.1
    # Version 1.1: InstanceFault version 1.2
    VERSION = '1.1'

    fields = {
        'objects': fields.ListOfObjectsField('InstanceFault'),
        }
    child_versions = {
        '1.0': '1.1',
        # NOTE(danms): InstanceFault was at 1.1 before we added this
        '1.1': '1.2',
        }

    @base.remotable_classmethod
    def get_by_instance_uuids(cls, context, instance_uuids):
        db_faultdict = db.instance_fault_get_by_instance_uuids(context,
                                                               instance_uuids)
        db_faultlist = itertools.chain(*db_faultdict.values())
        return base.obj_make_list(context, cls(context), objects.InstanceFault,
                                  db_faultlist)
