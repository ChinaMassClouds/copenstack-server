# Copyright 2011 Grid Dynamics
# Copyright 2011 OpenStack Foundation
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

import itertools
import os

from oslo.config import cfg
from webob import exc

from nova.api.openstack import common
from nova.api.openstack import extensions
from nova import compute
from nova import exception
from nova.i18n import _
from nova import utils

authorize = extensions.extension_authorizer('compute', 'fping')
authorize_all_tenants = extensions.extension_authorizer(
    'compute', 'fping:all_tenants')
fping_opts = [
    cfg.StrOpt("fping_path",
               default="/usr/sbin/fping",
               help="Full path to fping."),
]

CONF = cfg.CONF
CONF.register_opts(fping_opts)


class FpingController(object):

    def __init__(self, network_api=None):
        self.compute_api = compute.API()
        self.last_call = {}

    def check_fping(self):
        if not os.access(CONF.fping_path, os.X_OK):
            raise exc.HTTPServiceUnavailable(
                explanation=_("fping utility is not found."))

    @staticmethod
    def fping(ips):
        fping_ret = utils.execute(CONF.fping_path, *ips,
                                  check_exit_code=False)
        if not fping_ret:
            return set()
        alive_ips = set()
        for line in fping_ret[0].split("\n"):
            ip = line.split(" ", 1)[0]
            if "alive" in line:
                alive_ips.add(ip)
        return alive_ips

    @staticmethod
    def _get_instance_ips(context, instance):
        ret = []
        for network in common.get_networks_for_instance(
                context, instance).values():
            all_ips = itertools.chain(network["ips"], network["floating_ips"])
            ret += [ip["address"] for ip in all_ips]
        return ret

    def index(self, req):
        context = req.environ["nova.context"]
        search_opts = dict(deleted=False)
        if "all_tenants" in req.GET:
            authorize_all_tenants(context)
        else:
            authorize(context)
            if context.project_id:
                search_opts["project_id"] = context.project_id
            else:
                search_opts["user_id"] = context.user_id
        self.check_fping()
        include = req.GET.get("include", None)
        if include:
            include = set(include.split(","))
            exclude = set()
        else:
            include = None
            exclude = req.GET.get("exclude", None)
            if exclude:
                exclude = set(exclude.split(","))
            else:
                exclude = set()

        instance_list = self.compute_api.get_all(
            context, search_opts=search_opts)
        ip_list = []
        instance_ips = {}
        instance_projects = {}

        for instance in instance_list:
            uuid = instance["uuid"]
            if uuid in exclude or (include is not None and
                                   uuid not in include):
                continue
            ips = [str(ip) for ip in self._get_instance_ips(context, instance)]
            instance_ips[uuid] = ips
            instance_projects[uuid] = instance["project_id"]
            ip_list += ips
        alive_ips = self.fping(ip_list)
        res = []
        for instance_uuid, ips in instance_ips.iteritems():
            res.append({
                "id": instance_uuid,
                "project_id": instance_projects[instance_uuid],
                "alive": bool(set(ips) & alive_ips),
            })
        return {"servers": res}

    def show(self, req, id):
        try:
            context = req.environ["nova.context"]
            authorize(context)
            self.check_fping()
            instance = self.compute_api.get(context, id)
            ips = [str(ip) for ip in self._get_instance_ips(context, instance)]
            alive_ips = self.fping(ips)
            return {
                "server": {
                    "id": instance["uuid"],
                    "project_id": instance["project_id"],
                    "alive": bool(set(ips) & alive_ips),
                }
            }
        except exception.NotFound:
            raise exc.HTTPNotFound()


class Fping(extensions.ExtensionDescriptor):
    """Fping Management Extension."""

    name = "Fping"
    alias = "os-fping"
    namespace = "http://docs.openstack.org/compute/ext/fping/api/v1.1"
    updated = "2012-07-06T00:00:00Z"

    def get_resources(self):
        res = extensions.ResourceExtension(
            "os-fping",
            FpingController())
        return [res]
