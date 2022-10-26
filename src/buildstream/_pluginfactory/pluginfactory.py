#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
from typing import Tuple, Type, Iterator
from pluginbase import PluginSource

from .. import utils
from .. import _site
from ..plugin import Plugin
from ..source import Source
from ..element import Element
from ..node import Node
from ..utils import UtilError
from .._exceptions import PluginError
from .._messenger import Messenger

from .pluginorigin import PluginOrigin, PluginType


# A Context for loading plugin types
#
# Args:
#     plugin_base (PluginBase): The main PluginBase object to work with
#     plugin_type (PluginType): The type of plugin to load
#
# Since multiple pipelines can be processed recursively
# within the same interpretor, it's important that we have
# one context associated to the processing of a given pipeline,
# this way sources and element types which are particular to
# a given BuildStream project are isolated to their respective
# Pipelines.
#
class PluginFactory:
    def __init__(self, plugin_base, plugin_type):

        # For pickling across processes, make sure this context has a unique
        # identifier, which we prepend to the identifier of each PluginSource.
        # This keeps plugins loaded during the first and second pass distinct
        # from eachother.
        self._identifier = str(id(self))

        self._plugin_type = plugin_type  # The kind of plugins this factory loads
        self._types = {}  # Plugin type lookup table by kind
        self._origins = {}  # PluginOrigin lookup table by kind
        self._allow_deprecated = {}  # Lookup table to check if a plugin is allowed to be deprecated

        self._plugin_base = plugin_base  # The PluginBase object

        # The PluginSource objects need to be kept in scope for the lifetime
        # of the loaded plugins, otherwise the PluginSources delete the plugin
        # modules when they go out of scope.
        #
        # FIXME: Instead of keeping this table, we can call:
        #
        #            PluginBase.make_plugin_source(..., persist=True)
        #
        #        The persist attribute avoids this behavior. This is not currently viable
        #        because the BuildStream data model (projects and elements) does not properly
        #        go out of scope when the CLI completes, causing errors to occur when
        #        invoking BuildStream multiple times during tests.
        #
        self._sources = {}  #  A mapping of (location, kind) -> PluginSource objects

        self._init_site_source()

    # Initialize the PluginSource object for core plugins
    def _init_site_source(self):
        if self._plugin_type == PluginType.SOURCE:
            self._site_plugins_path = _site.source_plugins
        elif self._plugin_type == PluginType.ELEMENT:
            self._site_plugins_path = _site.element_plugins

        self._site_source = self._plugin_base.make_plugin_source(
            searchpath=[self._site_plugins_path],
            identifier=self._identifier + "site",
        )

    ######################################################
    #                  Public Methods                    #
    ######################################################

    # register_plugin_origin():
    #
    # Registers the PluginOrigin to use for the given plugin kind
    #
    # Args:
    #    kind (str): The kind identifier of the Plugin
    #    origin (PluginOrigin): The PluginOrigin providing the plugin
    #    allow_deprecated (bool): Whether this plugin kind is allowed to be used in a deprecated state
    #
    def register_plugin_origin(self, kind: str, origin: PluginOrigin, allow_deprecated: bool):
        if kind in self._origins:
            raise PluginError(
                "More than one {} plugin registered as kind '{}'".format(self._plugin_type, kind),
                reason="duplicate-plugin",
            )

        self._origins[kind] = origin
        self._allow_deprecated[kind] = allow_deprecated

    # lookup():
    #
    # Fetches a type loaded from a plugin in this plugin context
    #
    # Args:
    #     messenger (Messenger): The messenger
    #     kind (str): The kind of Plugin to create
    #     provenance_node (Node): The node from where the plugin was referenced
    #
    # Returns:
    #     (type): The type associated with the given kind
    #     (str): A path to the YAML file holding the plugin's defaults, or None
    #
    # Raises: PluginError
    #
    def lookup(self, messenger: Messenger, kind: str, provenance_node: Node) -> Tuple[Type[Plugin], str]:
        plugin_type, defaults = self._ensure_plugin(kind, provenance_node)

        # We can be called with None for the messenger here in the
        # case that we've been pickled through the scheduler (see jobpickler.py),
        #
        # In this case we know that we've already initialized and do not need
        # to warn about deprecated plugins a second time.
        if messenger is None:
            return plugin_type, defaults

        # After looking up the type, issue a warning if it's deprecated
        #
        # We do this here because we want to issue one warning for each time the
        # plugin is used.
        #
        if plugin_type.BST_PLUGIN_DEPRECATED and not self._allow_deprecated[kind]:
            messenger.warn(
                "{}: Using deprecated plugin '{}'".format(provenance_node.get_provenance(), kind),
                detail=plugin_type.BST_PLUGIN_DEPRECATION_MESSAGE,
            )

        return plugin_type, defaults

    # list_plugins():
    #
    # A generator which yields all of the plugins which have been loaded
    #
    # Yields:
    #    (str): The plugin kind
    #    (type): The loaded plugin type
    #    (str): The default yaml file, if any
    #    (str): The display string describing how the plugin was loaded
    #
    def list_plugins(self) -> Iterator[Tuple[str, Type[Plugin], str, str]]:
        for kind, (plugin_type, defaults, display) in self._types.items():
            yield kind, plugin_type, defaults, display

    # get_plugin_paths():
    #
    # Gets the directory on disk where the plugin itself is located,
    # and a full path to the plugin's accompanying YAML file for
    # it's defaults (if any).
    #
    # Args:
    #    kind (str): The plugin kind
    #
    # Returns:
    #    (str): The full path to the directory containing the plugin
    #    (str): The full path to the accompanying .yaml file containing
    #           the plugin's preferred defaults.
    #    (str): The explanatory display string describing how this plugin was loaded
    #
    def get_plugin_paths(self, kind: str):
        try:
            origin = self._origins[kind]
        except KeyError:
            return None, None, None

        return origin.get_plugin_paths(kind, self._plugin_type)

    ######################################################
    #                 Private Methods                    #
    ######################################################

    # _ensure_plugin():
    #
    # Ensures that a plugin is loaded, delegating the work of getting
    # the plugin materials from the respective PluginOrigin
    #
    # Args:
    #    kind (str): The plugin kind to load
    #    provenance (str): The provenance of whence the plugin was referred to in the project
    #
    # Returns:
    #    (type): The loaded type
    #    (str): The full path the the yaml file containing defaults, or None
    #
    # Raises:
    #    (PluginError): In case something went wrong loading the plugin
    #
    def _ensure_plugin(self, kind: str, provenance_node: Node) -> Tuple[Type[Plugin], str]:

        if kind not in self._types:

            # Get the directory on disk where the plugin exists, and
            # the optional accompanying .yaml file for the plugin, should
            # one have been provided.
            #
            location, defaults, display = self.get_plugin_paths(kind)

            if location:

                # Make the PluginSource object
                #
                source = self._plugin_base.make_plugin_source(
                    searchpath=[location],
                    identifier=self._identifier + location + kind,
                )

                # Keep a reference on the PluginSources (see comment in __init__)
                #
                self._sources[(location, kind)] = source
            else:
                # Try getting it from the core plugins
                if kind not in self._site_source.list_plugins():
                    raise PluginError(
                        "{}: No {} plugin registered for kind '{}'".format(
                            provenance_node.get_provenance(), self._plugin_type, kind
                        ),
                        reason="plugin-not-found",
                    )

                source = self._site_source
                defaults = os.path.join(self._site_plugins_path, "{}.yaml".format(kind))
                if not os.path.exists(defaults):
                    defaults = None
                display = "core plugin"

            self._types[kind] = (self._load_plugin(source, kind), defaults, display)

        type_, defaults, _ = self._types[kind]
        return type_, defaults

    # _load_plugin():
    #
    # Loads the actual plugin type from the PluginSource
    #
    # Args:
    #    source (PluginSource): The PluginSource
    #    kind (str): The plugin kind to load
    #
    # Returns:
    #    (type): The loaded type
    #
    # Raises:
    #    (PluginError): In case something went wrong loading the plugin
    #
    def _load_plugin(self, source: PluginSource, kind: str) -> Type[Plugin]:

        try:
            plugin = source.load_plugin(kind)

        except ImportError as e:
            raise PluginError("Failed to load {} plugin '{}': {}".format(self._plugin_type, kind, e)) from e

        try:
            plugin_type = plugin.setup()
        except AttributeError as e:
            raise PluginError(
                "{} plugin '{}' did not provide a setup() function".format(self._plugin_type, kind),
                reason="missing-setup-function",
            ) from e
        except TypeError as e:
            raise PluginError(
                "setup symbol in {} plugin '{}' is not a function".format(self._plugin_type, kind),
                reason="setup-is-not-function",
            ) from e

        self._assert_plugin(kind, plugin_type)
        self._assert_min_version(kind, plugin_type)

        return plugin_type

    # _assert_plugin():
    #
    # Performs assertions on the loaded plugin
    #
    # Args:
    #    kind (str): The plugin kind to load
    #    plugin_type (type): The loaded plugin type
    #
    # Raises:
    #    (PluginError): In case something went wrong loading the plugin
    #
    def _assert_plugin(self, kind: str, plugin_type: Type[Plugin]):
        if kind in self._types:
            raise PluginError(
                "Tried to register {} plugin for existing kind '{}' "
                "(already registered {})".format(self._plugin_type, kind, self._types[kind].__name__)
            )

        base_type: Type[Plugin]
        if self._plugin_type == PluginType.SOURCE:
            base_type = Source
        elif self._plugin_type == PluginType.ELEMENT:
            base_type = Element

        try:
            if not issubclass(plugin_type, base_type):
                raise PluginError(
                    "{} plugin '{}' returned type '{}', which is not a subclass of {}".format(
                        self._plugin_type, kind, plugin_type.__name__, base_type.__name__
                    ),
                    reason="setup-returns-bad-type",
                )
        except TypeError as e:
            raise PluginError(
                "{} plugin '{}' returned something that is not a type (expected subclass of {})".format(
                    self._plugin_type, kind, self._plugin_type
                ),
                reason="setup-returns-not-type",
            ) from e

    # _assert_min_version():
    #
    # Performs the version checks on the loaded plugin type,
    # ensuring that the loaded plugin is intended to work
    # with this version of BuildStream.
    #
    # Args:
    #    kind (str): The plugin kind to load
    #    plugin_type (type): The loaded plugin type
    #
    # Raises:
    #    (PluginError): In case something went wrong loading the plugin
    #
    def _assert_min_version(self, kind, plugin_type):

        if plugin_type.BST_MIN_VERSION is None:
            raise PluginError(
                "{} plugin '{}' did not specify BST_MIN_VERSION".format(self._plugin_type, kind),
                reason="missing-min-version",
                detail="Are you trying to use a BuildStream 1 plugin with a BuildStream 2 project ?",
            )

        try:
            min_version_major, min_version_minor = utils._parse_version(plugin_type.BST_MIN_VERSION)
        except UtilError as e:
            raise PluginError(
                "{} plugin '{}' specified malformed BST_MIN_VERSION: {}".format(
                    self._plugin_type, kind, plugin_type.BST_MIN_VERSION
                ),
                reason="malformed-min-version",
                detail="BST_MIN_VERSION must be specified as 'MAJOR.MINOR' with "
                + "numeric major and minor minimum required version numbers",
            ) from e

        bst_major, bst_minor = utils._get_bst_api_version()

        if min_version_major != bst_major:
            raise PluginError(
                "{} plugin '{}' requires BuildStream {}, but is being loaded with BuildStream {}".format(
                    self._plugin_type, kind, min_version_major, bst_major
                ),
                reason="incompatible-major-version",
                detail="You will need to find the correct version of this plugin for your project.",
            )

        if min_version_minor > bst_minor:
            raise PluginError(
                "{} plugin '{}' requires BuildStream {}, but is being loaded with BuildStream {}.{}".format(
                    self._plugin_type, kind, plugin_type.BST_MIN_VERSION, bst_major, bst_minor
                ),
                reason="incompatible-minor-version",
                detail="Please upgrade to BuildStream {}".format(plugin_type.BST_MIN_VERSION),
            )
