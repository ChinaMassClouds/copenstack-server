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
from nova.objects import base
from nova.objects import fields


class BandwidthUsage(base.NovaPersistentObject, base.NovaObject):
    # Version 1.0: Initial version
    # Version 1.1: Add use_slave to get_by_instance_uuid_and_mac
    VERSION = '1.1'

    fields = {
        'instance_uuid': fields.UUIDField(),
        'mac': fields.StringField(),
        'start_period': fields.DateTimeField(),
        'last_refreshed': fields.DateTimeField(),
        'bw_in': fields.IntegerField(),
        'bw_out': fields.IntegerField(),
        'last_ctr_in': fields.IntegerField(),
        'last_ctr_out': fields.IntegerField()
    }

    @staticmethod
    def _from_db_object(context, bw_usage, db_bw_usage):
        for field in bw_usage.fields:
            bw_usage[field] = db_bw_usage[field]
        bw_usage._context = context
        bw_usage.obj_reset_changes()
        return bw_usage

    @base.serialize_args
    @base.remotable_classmethod
    def get_by_instance_uuid_and_mac(cls, context, instance_uuid, mac,
                                     start_period=None, use_slave=False):
        db_bw_usage = db.bw_usage_get(context, uuid=instance_uuid,
                                      start_period=start_period, mac=mac,
                                      use_slave=use_slave)
        if db_bw_usage:
            return cls._from_db_object(context, cls(), db_bw_usage)

    @base.serialize_args
    @base.remotable
    def create(self, context, uuid, mac, bw_in, bw_out, last_ctr_in,
               last_ctr_out, start_period=None, last_refreshed=None):
        db_bw_usage = db.bw_usage_update(
            context, uuid, mac, start_period, bw_in, bw_out,
            last_ctr_in, last_ctr_out, last_refreshed=last_refreshed)

        self._from_db_object(context, self, db_bw_usage)


class BandwidthUsageList(base.ObjectListBase, base.NovaObject):
    # Version 1.0: Initial version
    # Version 1.1: Add use_slave to get_by_uuids
    VERSION = '1.1'
    fields = {
        'objects': fields.ListOfObjectsField('BandwidthUsage'),
    }
    child_versions = {
        '1.0': '1.0',
        '1.1': '1.1',
    }

    @base.serialize_args
    @base.remotable_classmethod
    def get_by_uuids(cls, context, uuids, start_period=None, use_slave=False):
        db_bw_usages = db.bw_usage_get_by_uuids(context, uuids=uuids,
                                                start_period=start_period,
                                                use_slave=use_slave)
        return base.obj_make_list(context, cls(), BandwidthUsage, db_bw_usages)
