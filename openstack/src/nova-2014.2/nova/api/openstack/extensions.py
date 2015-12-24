# Copyright 2011 OpenStack Foundation
# Copyright 2011 Justin Santa Barbara
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

import abc
import functools
import os

import six
import webob.dec
import webob.exc

import nova.api.openstack
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import exception
from nova.i18n import _
from nova.i18n import _LW
from nova.openstack.common import importutils
from nova.openstack.common import log as logging
import nova.policy

LOG = logging.getLogger(__name__)


class ExtensionDescriptor(object):
    """Base class that defines the contract for extensions.

    Note that you don't have to derive from this class to have a valid
    extension; it is purely a convenience.

    """

    # The name of the extension, e.g., 'Fox In Socks'
    name = None

    # The alias for the extension, e.g., 'FOXNSOX'
    alias = None

    # Description comes from the docstring for the class

    # The XML namespace for the extension, e.g.,
    # 'http://www.fox.in.socks/api/ext/pie/v1.0'
    namespace = None

    # The timestamp when the extension was last updated, e.g.,
    # '2011-01-22T19:25:27Z'
    updated = None

    def __init__(self, ext_mgr):
        """Register extension with the extension manager."""

        ext_mgr.register(self)
        self.ext_mgr = ext_mgr

    def get_resources(self):
        """List of extensions.ResourceExtension extension objects.

        Resources define new nouns, and are accessible through URLs.

        """
        resources = []
        return resources

    def get_controller_extensions(self):
        """List of extensions.ControllerExtension extension objects.

        Controller extensions are used to extend existing controllers.
        """
        controller_exts = []
        return controller_exts

    @classmethod
    def nsmap(cls):
        """Synthesize a namespace map from extension."""

        # Start with a base nsmap
        nsmap = ext_nsmap.copy()

        # Add the namespace for the extension
        nsmap[cls.alias] = cls.namespace

        return nsmap

    @classmethod
    def xmlname(cls, name):
        """Synthesize element and attribute names."""

        return '{%s}%s' % (cls.namespace, name)


def make_ext(elem):
    elem.set('name')
    elem.set('namespace')
    elem.set('alias')
    elem.set('updated')

    desc = xmlutil.SubTemplateElement(elem, 'description')
    desc.text = 'description'

    xmlutil.make_links(elem, 'links')


ext_nsmap = {None: xmlutil.XMLNS_COMMON_V10, 'atom': xmlutil.XMLNS_ATOM}


class ExtensionTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('extension', selector='extension')
        make_ext(root)
        return xmlutil.MasterTemplate(root, 1, nsmap=ext_nsmap)


class ExtensionsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('extensions')
        elem = xmlutil.SubTemplateElement(root, 'extension',
                                          selector='extensions')
        make_ext(elem)
        return xmlutil.MasterTemplate(root, 1, nsmap=ext_nsmap)


class ExtensionsController(wsgi.Resource):

    def __init__(self, extension_manager):
        self.extension_manager = extension_manager
        super(ExtensionsController, self).__init__(None)

    def _translate(self, ext):
        ext_data = {}
        ext_data['name'] = ext.name
        ext_data['alias'] = ext.alias
        ext_data['description'] = ext.__doc__
        ext_data['namespace'] = ext.namespace
        ext_data['updated'] = ext.updated
        ext_data['links'] = []  # TODO(dprince): implement extension links
        return ext_data

    @wsgi.serializers(xml=ExtensionsTemplate)
    def index(self, req):
        extensions = []
        for ext in self.extension_manager.sorted_extensions():
            extensions.append(self._translate(ext))
        return dict(extensions=extensions)

    @wsgi.serializers(xml=ExtensionTemplate)
    def show(self, req, id):
        try:
            # NOTE(dprince): the extensions alias is used as the 'id' for show
            ext = self.extension_manager.extensions[id]
        except KeyError:
            raise webob.exc.HTTPNotFound()

        return dict(extension=self._translate(ext))

    def delete(self, req, id):
        raise webob.exc.HTTPNotFound()

    def create(self, req, body):
        raise webob.exc.HTTPNotFound()


class ExtensionManager(object):
    """Load extensions from the configured extension path.

    See nova/tests/api/openstack/compute/extensions/foxinsocks.py or an
    example extension implementation.

    """
    def sorted_extensions(self):
        if self.sorted_ext_list is None:
            self.sorted_ext_list = sorted(self.extensions.iteritems())

        for _alias, ext in self.sorted_ext_list:
            yield ext

    def is_loaded(self, alias):
        return alias in self.extensions

    def register(self, ext):
        # Do nothing if the extension doesn't check out
        if not self._check_extension(ext):
            return

        alias = ext.alias
        if alias in self.extensions:
            raise exception.NovaException("Found duplicate extension: %s"
                                          % alias)
        self.extensions[alias] = ext
        self.sorted_ext_list = None

    def get_resources(self):
        """Returns a list of ResourceExtension objects."""

        resources = []
        resources.append(ResourceExtension('extensions',
                                           ExtensionsController(self)))
        for ext in self.sorted_extensions():
            try:
                resources.extend(ext.get_resources())
            except AttributeError:
                # NOTE(dprince): Extension aren't required to have resource
                # extensions
                pass
        return resources

    def get_controller_extensions(self):
        """Returns a list of ControllerExtension objects."""
        controller_exts = []
        for ext in self.sorted_extensions():
            try:
                get_ext_method = ext.get_controller_extensions
            except AttributeError:
                # NOTE(Vek): Extensions aren't required to have
                # controller extensions
                continue
            controller_exts.extend(get_ext_method())
        return controller_exts

    def _check_extension(self, extension):
        """Checks for required methods in extension objects."""
        try:
            LOG.debug('Ext name: %s', extension.name)
            LOG.debug('Ext alias: %s', extension.alias)
            LOG.debug('Ext description: %s',
                      ' '.join(extension.__doc__.strip().split()))
            LOG.debug('Ext namespace: %s', extension.namespace)
            LOG.debug('Ext updated: %s', extension.updated)
        except AttributeError as ex:
            LOG.exception(_("Exception loading extension: %s"), unicode(ex))
            return False

        return True

    def load_extension(self, ext_factory):
        """Execute an extension factory.

        Loads an extension.  The 'ext_factory' is the name of a
        callable that will be imported and called with one
        argument--the extension manager.  The factory callable is
        expected to call the register() method at least once.
        """

        LOG.debug("Loading extension %s", ext_factory)

        if isinstance(ext_factory, six.string_types):
            # Load the factory
            factory = importutils.import_class(ext_factory)
        else:
            factory = ext_factory

        # Call it
        LOG.debug("Calling extension factory %s", ext_factory)
        factory(self)

    def _load_extensions(self):
        """Load extensions specified on the command line."""

        extensions = list(self.cls_list)

        for ext_factory in extensions:
            try:
                self.load_extension(ext_factory)
            except Exception as exc:
                LOG.warn(_LW('Failed to load extension %(ext_factory)s: '
                             '%(exc)s'),
                         {'ext_factory': ext_factory, 'exc': exc})


class ControllerExtension(object):
    """Extend core controllers of nova OpenStack API.

    Provide a way to extend existing nova OpenStack API core
    controllers.
    """

    def __init__(self, extension, collection, controller):
        self.extension = extension
        self.collection = collection
        self.controller = controller


class ResourceExtension(object):
    """Add top level resources to the OpenStack API in nova."""

    def __init__(self, collection, controller=None, parent=None,
                 collection_actions=None, member_actions=None,
                 custom_routes_fn=None, inherits=None, member_name=None):
        if not collection_actions:
            collection_actions = {}
        if not member_actions:
            member_actions = {}
        self.collection = collection
        self.controller = controller
        self.parent = parent
        self.collection_actions = collection_actions
        self.member_actions = member_actions
        self.custom_routes_fn = custom_routes_fn
        self.inherits = inherits
        self.member_name = member_name


def load_standard_extensions(ext_mgr, logger, path, package, ext_list=None):
    """Registers all standard API extensions."""

    # Walk through all the modules in our directory...
    our_dir = path[0]
    for dirpath, dirnames, filenames in os.walk(our_dir):
        # Compute the relative package name from the dirpath
        relpath = os.path.relpath(dirpath, our_dir)
        if relpath == '.':
            relpkg = ''
        else:
            relpkg = '.%s' % '.'.join(relpath.split(os.sep))

        # Now, consider each file in turn, only considering .py files
        for fname in filenames:
            root, ext = os.path.splitext(fname)

            # Skip __init__ and anything that's not .py
            if ext != '.py' or root == '__init__':
                continue

            # Try loading it
            classname = "%s%s" % (root[0].upper(), root[1:])
            classpath = ("%s%s.%s.%s" %
                         (package, relpkg, root, classname))

            if ext_list is not None and classname not in ext_list:
                logger.debug("Skipping extension: %s" % classpath)
                continue

            try:
                ext_mgr.load_extension(classpath)
            except Exception as exc:
                logger.warn(_('Failed to load extension %(classpath)s: '
                              '%(exc)s'),
                            {'classpath': classpath, 'exc': exc})

        # Now, let's consider any subdirectories we may have...
        subdirs = []
        for dname in dirnames:
            # Skip it if it does not have __init__.py
            if not os.path.exists(os.path.join(dirpath, dname, '__init__.py')):
                continue

            # If it has extension(), delegate...
            ext_name = "%s%s.%s.extension" % (package, relpkg, dname)
            try:
                ext = importutils.import_class(ext_name)
            except ImportError:
                # extension() doesn't exist on it, so we'll explore
                # the directory for ourselves
                subdirs.append(dname)
            else:
                try:
                    ext(ext_mgr)
                except Exception as exc:
                    logger.warn(_('Failed to load extension %(ext_name)s:'
                                  '%(exc)s'),
                                {'ext_name': ext_name, 'exc': exc})

        # Update the list of directories we'll explore...
        dirnames[:] = subdirs


def core_authorizer(api_name, extension_name):
    def authorize(context, target=None, action=None):
        if target is None:
            target = {'project_id': context.project_id,
                      'user_id': context.user_id}
        if action is None:
            act = '%s:%s' % (api_name, extension_name)
        else:
            act = '%s:%s:%s' % (api_name, extension_name, action)
        nova.policy.enforce(context, act, target)
    return authorize


def extension_authorizer(api_name, extension_name):
    return core_authorizer('%s_extension' % api_name, extension_name)


def soft_authorizer(hard_authorizer, api_name, extension_name):
    hard_authorize = hard_authorizer(api_name, extension_name)

    def authorize(context, action=None):
        try:
            hard_authorize(context, action=action)
            return True
        except exception.Forbidden:
            return False
    return authorize


def soft_extension_authorizer(api_name, extension_name):
    return soft_authorizer(extension_authorizer, api_name, extension_name)


def soft_core_authorizer(api_name, extension_name):
    return soft_authorizer(core_authorizer, api_name, extension_name)


def check_compute_policy(context, action, target, scope='compute'):
    _action = '%s:%s' % (scope, action)
    nova.policy.enforce(context, _action, target)


@six.add_metaclass(abc.ABCMeta)
class V3APIExtensionBase(object):
    """Abstract base class for all V3 API extensions.

    All V3 API extensions must derive from this class and implement
    the abstract methods get_resources and get_controller_extensions
    even if they just return an empty list. The extensions must also
    define the abstract properties.
    """

    def __init__(self, extension_info):
        self.extension_info = extension_info

    @abc.abstractmethod
    def get_resources(self):
        """Return a list of resources extensions.

        The extensions should return a list of ResourceExtension
        objects. This list may be empty.
        """
        pass

    @abc.abstractmethod
    def get_controller_extensions(self):
        """Return a list of controller extensions.

        The extensions should return a list of ControllerExtension
        objects. This list may be empty.
        """
        pass

    @abc.abstractproperty
    def name(self):
        """Name of the extension."""
        pass

    @abc.abstractproperty
    def alias(self):
        """Alias for the extension."""
        pass

    @abc.abstractproperty
    def version(self):
        """Version of the extension."""
        pass


def expected_errors(errors):
    """Decorator for v3 API methods which specifies expected exceptions.

    Specify which exceptions may occur when an API method is called. If an
    unexpected exception occurs then return a 500 instead and ask the user
    of the API to file a bug report.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as exc:
                if isinstance(exc, webob.exc.WSGIHTTPException):
                    if isinstance(errors, int):
                        t_errors = (errors,)
                    else:
                        t_errors = errors
                    if exc.code in t_errors:
                        raise
                elif isinstance(exc, exception.PolicyNotAuthorized):
                    # Note(cyeoh): Special case to handle
                    # PolicyNotAuthorized exceptions so every
                    # extension method does not need to wrap authorize
                    # calls. ResourceExceptionHandler silently
                    # converts NotAuthorized to HTTPForbidden
                    raise
                elif isinstance(exc, exception.ValidationError):
                    # Note(oomichi): Handle a validation error, which
                    # happens due to invalid API parameters, as an
                    # expected error.
                    raise

                LOG.exception(_("Unexpected exception in API method"))
                msg = _('Unexpected API Error. Please report this at '
                    'http://bugs.launchpad.net/nova/ and attach the Nova '
                    'API log if possible.\n%s') % type(exc)
                raise webob.exc.HTTPInternalServerError(explanation=msg)

        return wrapped

    return decorator
