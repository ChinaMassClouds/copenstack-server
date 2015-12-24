# Copyright (c) 2012 OpenStack Foundation
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

from nova.compute import task_states
from nova.compute import vm_states
from nova.i18n import _
from nova.openstack.common import jsonutils


class Stats(dict):
    """Handler for updates to compute node workload stats."""

    def __init__(self):
        super(Stats, self).__init__()

        # Track instance states for compute node workload calculations:
        self.states = {}

    def clear(self):
        super(Stats, self).clear()

        self.states.clear()

    def digest_stats(self, stats):
        """Apply stats provided as a dict or a json encoded string."""
        # NOTE(pmurray): allow json strings as some drivers pass in
        # stats in that way - they shouldn't really do that.
        if stats is None:
            return
        if isinstance(stats, dict):
            self.update(stats)
            return
        if isinstance(stats, str):
            _stats_from_json = jsonutils.loads(stats)
            self.update(_stats_from_json)
            return
        raise ValueError(_('Unexpected type adding stats'))

    @property
    def io_workload(self):
        """Calculate an I/O based load by counting I/O heavy operations."""

        def _get(state, state_type):
            key = "num_%s_%s" % (state_type, state)
            return self.get(key, 0)

        num_builds = _get(vm_states.BUILDING, "vm")
        num_migrations = _get(task_states.RESIZE_MIGRATING, "task")
        num_rebuilds = _get(task_states.REBUILDING, "task")
        num_resizes = _get(task_states.RESIZE_PREP, "task")
        num_snapshots = _get(task_states.IMAGE_SNAPSHOT, "task")
        num_backups = _get(task_states.IMAGE_BACKUP, "task")
        num_rescues = _get(task_states.RESCUING, "task")
        num_unshelves = _get(task_states.UNSHELVING, "task")

        return (num_builds + num_rebuilds + num_resizes + num_migrations +
                num_snapshots + num_backups + num_rescues + num_unshelves)

    def calculate_workload(self):
        """Calculate current load of the compute host based on
        task states.
        """
        current_workload = 0
        for k in self:
            if k.startswith("num_task") and not k.endswith("None"):
                current_workload += self[k]
        return current_workload

    @property
    def num_instances(self):
        return self.get("num_instances", 0)

    def num_instances_for_project(self, project_id):
        key = "num_proj_%s" % project_id
        return self.get(key, 0)

    def num_os_type(self, os_type):
        key = "num_os_type_%s" % os_type
        return self.get(key, 0)

    def update_stats_for_instance(self, instance):
        """Update stats after an instance is changed."""

        uuid = instance['uuid']

        # First, remove stats from the previous instance
        # state:
        if uuid in self.states:
            old_state = self.states[uuid]

            self._decrement("num_vm_%s" % old_state['vm_state'])
            self._decrement("num_task_%s" % old_state['task_state'])
            self._decrement("num_os_type_%s" % old_state['os_type'])
            self._decrement("num_proj_%s" % old_state['project_id'])
        else:
            # new instance
            self._increment("num_instances")

        # Now update stats from the new instance state:
        (vm_state, task_state, os_type, project_id) = \
                self._extract_state_from_instance(instance)

        if vm_state == vm_states.DELETED:
            self._decrement("num_instances")
            self.states.pop(uuid)

        else:
            self._increment("num_vm_%s" % vm_state)
            self._increment("num_task_%s" % task_state)
            self._increment("num_os_type_%s" % os_type)
            self._increment("num_proj_%s" % project_id)

        # save updated I/O workload in stats:
        self["io_workload"] = self.io_workload

    def _decrement(self, key):
        x = self.get(key, 0)
        self[key] = x - 1

    def _increment(self, key):
        x = self.get(key, 0)
        self[key] = x + 1

    def _extract_state_from_instance(self, instance):
        """Save the useful bits of instance state for tracking purposes."""

        uuid = instance['uuid']
        vm_state = instance['vm_state']
        task_state = instance['task_state']
        os_type = instance['os_type']
        project_id = instance['project_id']

        self.states[uuid] = dict(vm_state=vm_state, task_state=task_state,
                                 os_type=os_type, project_id=project_id)

        return (vm_state, task_state, os_type, project_id)
