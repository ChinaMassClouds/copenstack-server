# Copyright 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import webob
from webob import exc

from nova.api.openstack import common
from nova.api.openstack.compute.schemas.v3 import migrate_server
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api import validation
from nova import compute
from nova import exception
from nova.openstack.common import strutils

ALIAS = "os-migrate-server"


def authorize(context, action_name):
    action = 'v3:%s:%s' % (ALIAS, action_name)
    extensions.extension_authorizer('compute', action)(context)


class MigrateServerController(wsgi.Controller):
    def __init__(self, *args, **kwargs):
        super(MigrateServerController, self).__init__(*args, **kwargs)
        self.compute_api = compute.API()

    @extensions.expected_errors((400, 403, 404, 409))
    @wsgi.action('migrate')
    def _migrate(self, req, id, body):
        """Permit admins to migrate a server to a new host."""
        context = req.environ['nova.context']
        authorize(context, 'migrate')

        instance = common.get_instance(self.compute_api, context, id,
                                       want_objects=True)
        try:
            self.compute_api.resize(req.environ['nova.context'], instance)
        except (exception.TooManyInstances, exception.QuotaError) as e:
            raise exc.HTTPForbidden(explanation=e.format_message())
        except exception.InstanceIsLocked as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.InstanceInvalidState as state_error:
            common.raise_http_conflict_for_instance_invalid_state(state_error,
                    'migrate')
        except exception.InstanceNotFound as e:
            raise exc.HTTPNotFound(explanation=e.format_message())
        except exception.NoValidHost as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

        return webob.Response(status_int=202)

    @extensions.expected_errors((400, 404, 409))
    @wsgi.action('os-migrateLive')
    @validation.schema(migrate_server.migrate_live)
    def _migrate_live(self, req, id, body):
        """Permit admins to (live) migrate a server to a new host."""
        context = req.environ["nova.context"]
        authorize(context, 'migrate_live')

        block_migration = body["os-migrateLive"]["block_migration"]
        disk_over_commit = body["os-migrateLive"]["disk_over_commit"]
        host = body["os-migrateLive"]["host"]

        block_migration = strutils.bool_from_string(block_migration,
                                                    strict=True)
        disk_over_commit = strutils.bool_from_string(disk_over_commit,
                                                     strict=True)

        try:
            instance = common.get_instance(self.compute_api, context, id,
                                           want_objects=True)
            self.compute_api.live_migrate(context, instance, block_migration,
                                          disk_over_commit, host)
        except (exception.NoValidHost,
                exception.ComputeServiceUnavailable,
                exception.InvalidHypervisorType,
                exception.InvalidCPUInfo,
                exception.UnableToMigrateToSelf,
                exception.DestinationHypervisorTooOld,
                exception.InvalidLocalStorage,
                exception.InvalidSharedStorage,
                exception.HypervisorUnavailable,
                exception.InstanceNotRunning,
                exception.MigrationPreCheckError,
                exception.LiveMigrationWithOldNovaNotSafe) as ex:
            raise exc.HTTPBadRequest(explanation=ex.format_message())
        except exception.InstanceIsLocked as e:
            raise exc.HTTPConflict(explanation=e.format_message())
        except exception.InstanceInvalidState as state_error:
            common.raise_http_conflict_for_instance_invalid_state(state_error,
                    'os-migrateLive')
        return webob.Response(status_int=202)


class MigrateServer(extensions.V3APIExtensionBase):
    """Enable migrate and live-migrate server actions."""

    name = "MigrateServer"
    alias = ALIAS
    version = 1

    def get_controller_extensions(self):
        controller = MigrateServerController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]

    def get_resources(self):
        return []
