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

from webob import exc

from nova.api.openstack import common
from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import exception
from nova.i18n import _
import nova.image

ALIAS = 'image-metadata'


class ImageMetadataController(object):
    """The image metadata API controller for the OpenStack API."""

    def __init__(self):
        self.image_api = nova.image.API()

    def _get_image(self, context, image_id):
        try:
            return self.image_api.get(context, image_id)
        except exception.ImageNotAuthorized as e:
            raise exc.HTTPForbidden(explanation=e.format_message())
        except exception.ImageNotFound:
            msg = _("Image not found.")
            raise exc.HTTPNotFound(explanation=msg)

    @extensions.expected_errors((403, 404))
    def index(self, req, image_id):
        """Returns the list of metadata for a given instance."""
        context = req.environ['nova.context']
        metadata = self._get_image(context, image_id)['properties']
        return dict(metadata=metadata)

    @extensions.expected_errors((403, 404))
    def show(self, req, image_id, id):
        context = req.environ['nova.context']
        metadata = self._get_image(context, image_id)['properties']
        if id in metadata:
            return {'meta': {id: metadata[id]}}
        else:
            raise exc.HTTPNotFound()

    @extensions.expected_errors((400, 403, 404, 413))
    def create(self, req, image_id, body):
        context = req.environ['nova.context']
        image = self._get_image(context, image_id)
        if 'metadata' in body:
            for key, value in body['metadata'].iteritems():
                image['properties'][key] = value
        common.check_img_metadata_properties_quota(context,
                                                   image['properties'])
        try:
            image = self.image_api.update(context, image_id, image, data=None,
                                          purge_props=True)
        except exception.ImageNotAuthorized as e:
            raise exc.HTTPForbidden(explanation=e.format_message())
        return dict(metadata=image['properties'])

    @extensions.expected_errors((400, 403, 404, 413))
    def update(self, req, image_id, id, body):
        context = req.environ['nova.context']

        try:
            meta = body['meta']
        except KeyError:
            expl = _('Incorrect request body format')
            raise exc.HTTPBadRequest(explanation=expl)

        if id not in meta:
            expl = _('Request body and URI mismatch')
            raise exc.HTTPBadRequest(explanation=expl)
        if len(meta) > 1:
            expl = _('Request body contains too many items')
            raise exc.HTTPBadRequest(explanation=expl)

        image = self._get_image(context, image_id)
        image['properties'][id] = meta[id]
        common.check_img_metadata_properties_quota(context,
                                                   image['properties'])
        try:
            self.image_api.update(context, image_id, image, data=None,
                                  purge_props=True)
        except exception.ImageNotAuthorized as e:
            raise exc.HTTPForbidden(explanation=e.format_message())
        return dict(meta=meta)

    @extensions.expected_errors((400, 403, 404, 413))
    def update_all(self, req, image_id, body):
        context = req.environ['nova.context']
        image = self._get_image(context, image_id)
        metadata = body.get('metadata', {})
        common.check_img_metadata_properties_quota(context, metadata)
        image['properties'] = metadata
        try:
            self.image_api.update(context, image_id, image, data=None,
                                  purge_props=True)
        except exception.ImageNotAuthorized as e:
            raise exc.HTTPForbidden(explanation=e.format_message())
        return dict(metadata=metadata)

    @extensions.expected_errors((403, 404))
    @wsgi.response(204)
    def delete(self, req, image_id, id):
        context = req.environ['nova.context']
        image = self._get_image(context, image_id)
        if id not in image['properties']:
            msg = _("Invalid metadata key")
            raise exc.HTTPNotFound(explanation=msg)
        image['properties'].pop(id)
        try:
            self.image_api.update(context, image_id, image, data=None,
                                  purge_props=True)
        except exception.ImageNotAuthorized as e:
            raise exc.HTTPForbidden(explanation=e.format_message())


class ImageMetadata(extensions.V3APIExtensionBase):
    """Image Metadata API."""
    name = "ImageMetadata"
    alias = ALIAS
    version = 1

    def get_resources(self):
        parent = {'member_name': 'image',
                  'collection_name': 'images'}
        resources = [extensions.ResourceExtension('metadata',
                                                  ImageMetadataController(),
                                                  member_name='image_meta',
                                                  parent=parent,
                                                  custom_routes_fn=
                                                  self.image_metadata_map
                                                  )]
        return resources

    def get_controller_extensions(self):
        return []

    def image_metadata_map(self, mapper, wsgi_resource):
        mapper.connect("metadata", "/images/{image_id}/metadata",
                       controller=wsgi_resource,
                       action='update_all', conditions={"method": ['PUT']})
