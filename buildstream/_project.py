#
#  Copyright (C) 2016-2018 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
import multiprocessing  # for cpu_count()
from collections import Mapping
from pluginbase import PluginBase
from . import utils
from . import _cachekey
from . import _site
from . import _yaml
from ._profile import Topics, profile_start, profile_end
from ._exceptions import LoadError, LoadErrorReason
from ._options import OptionPool
from ._artifactcache import ArtifactCache
from ._elementfactory import ElementFactory
from ._sourcefactory import SourceFactory
from ._projectrefs import ProjectRefs, ProjectRefStorage
from ._versions import BST_FORMAT_VERSION
from ._loader import Loader
from ._includes import Includes
from .element import Element
from ._message import Message, MessageType


# The separator we use for user specified aliases
_ALIAS_SEPARATOR = ':'

# Project Configuration file
_PROJECT_CONF_FILE = 'project.conf'


# HostMount()
#
# A simple object describing the behavior of
# a host mount.
#
class HostMount():

    def __init__(self, path, host_path=None, optional=False):

        # Support environment variable expansion in host mounts
        path = os.path.expandvars(path)
        if host_path is not None:
            host_path = os.path.expandvars(host_path)

        self.path = path              # Path inside the sandbox
        self.host_path = host_path    # Path on the host
        self.optional = optional      # Optional mounts do not incur warnings or errors

        if self.host_path is None:
            self.host_path = self.path


class PluginCollection:

    def __init__(self, project, context, directory, config):
        self._project = project
        self._context = context
        self._directory = directory
        self._plugin_source_origins = []   # Origins of custom sources
        self._plugin_element_origins = []  # Origins of custom elements

        # Plugin origins and versions
        origins = _yaml.node_get(config, list, 'plugins', default_value=[])
        self._source_format_versions = {}
        self._element_format_versions = {}
        for origin in origins:
            allowed_origin_fields = [
                'origin', 'sources', 'elements',
                'package-name', 'path',
            ]
            allowed_origins = ['core', 'local', 'pip']
            _yaml.node_validate(origin, allowed_origin_fields)

            if origin['origin'] not in allowed_origins:
                raise LoadError(
                    LoadErrorReason.INVALID_YAML,
                    "Origin '{}' is not one of the allowed types"
                    .format(origin['origin']))

            # Store source versions for checking later
            source_versions = _yaml.node_get(origin, Mapping, 'sources', default_value={})
            for key, _ in _yaml.node_items(source_versions):
                if key in self._source_format_versions:
                    raise LoadError(
                        LoadErrorReason.INVALID_YAML,
                        "Duplicate listing of source '{}'".format(key))
                self._source_format_versions[key] = _yaml.node_get(source_versions, int, key)

            # Store element versions for checking later
            element_versions = _yaml.node_get(origin, Mapping, 'elements', default_value={})
            for key, _ in _yaml.node_items(element_versions):
                if key in self._element_format_versions:
                    raise LoadError(
                        LoadErrorReason.INVALID_YAML,
                        "Duplicate listing of element '{}'".format(key))
                self._element_format_versions[key] = _yaml.node_get(element_versions, int, key)

            # Store the origins if they're not 'core'.
            # core elements are loaded by default, so storing is unnecessary.
            if _yaml.node_get(origin, str, 'origin') != 'core':
                self._store_origin(origin, 'sources', self._plugin_source_origins)
                self._store_origin(origin, 'elements', self._plugin_element_origins)

        pluginbase = PluginBase(package='buildstream.plugins')
        self._element_factory = ElementFactory(pluginbase, self._plugin_element_origins)
        self._source_factory = SourceFactory(pluginbase, self._plugin_source_origins)

    # _store_origin()
    #
    # Helper function to store plugin origins
    #
    # Args:
    #    origin (dict) - a dictionary indicating the origin of a group of
    #                    plugins.
    #    plugin_group (str) - The name of the type of plugin that is being
    #                         loaded
    #    destination (list) - A list of dicts to store the origins in
    #
    # Raises:
    #    LoadError if 'origin' is an unexpected value
    def _store_origin(self, origin, plugin_group, destination):
        expected_groups = ['sources', 'elements']
        if plugin_group not in expected_groups:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "Unexpected plugin group: {}, expecting {}"
                            .format(plugin_group, expected_groups))
        if plugin_group in origin:
            origin_dict = _yaml.node_copy(origin)
            plugins = _yaml.node_get(origin, Mapping, plugin_group, default_value={})
            origin_dict['plugins'] = [k for k, _ in _yaml.node_items(plugins)]
            for group in expected_groups:
                if group in origin_dict:
                    del origin_dict[group]
            if origin_dict['origin'] == 'local':
                # paths are passed in relative to the project, but must be absolute
                origin_dict['path'] = os.path.join(self._directory, origin_dict['path'])
            destination.append(origin_dict)

    # create_element()
    #
    # Instantiate and return an element
    #
    # Args:
    #    artifacts (ArtifactCache): The artifact cache
    #    meta (MetaElement): The loaded MetaElement
    #
    # Returns:
    #    (Element): A newly created Element object of the appropriate kind
    #
    def create_element(self, artifacts, meta):
        element = self._element_factory.create(self._context, self._project, artifacts, meta)
        version = self._element_format_versions.get(meta.kind, 0)
        self._assert_plugin_format(element, version)
        return element

    # create_source()
    #
    # Instantiate and return a Source
    #
    # Args:
    #    meta (MetaSource): The loaded MetaSource
    #
    # Returns:
    #    (Source): A newly created Source object of the appropriate kind
    #
    def create_source(self, meta):
        source = self._source_factory.create(self._context, self._project, meta)
        version = self._source_format_versions.get(meta.kind, 0)
        self._assert_plugin_format(source, version)
        return source

    # _assert_plugin_format()
    #
    # Helper to raise a PluginError if the loaded plugin is of a lesser version then
    # the required version for this plugin
    #
    def _assert_plugin_format(self, plugin, version):
        if plugin.BST_FORMAT_VERSION < version:
            raise LoadError(LoadErrorReason.UNSUPPORTED_PLUGIN,
                            "{}: Format version {} is too old for requested version {}"
                            .format(plugin, plugin.BST_FORMAT_VERSION, version))


class ProjectConfig:
    def __init__(self):
        self.plugins = None
        self.options = None                      # OptionPool
        self.base_variables = {}                 # The base set of variables
        self.element_overrides = {}              # Element specific configurations
        self.source_overrides = {}               # Source specific configurations


# Project()
#
# The Project Configuration
#
class Project():

    INCLUDE_CONFIG_KEYS = ['variables',
                           'environment', 'environment-nocache',
                           'split-rules', 'elements', 'plugins',
                           'aliases', 'artifacts',
                           'fail-on-overlap', 'shell',
                           'ref-storage', 'sandbox',
                           'options']

    MAIN_FILE_CONFIG_KEYS = ['format-version',
                             'element-path',
                             'name']

    def __init__(self, directory, context, *, junction=None, cli_options=None,
                 parent_loader=None, tempdir=None):

        # The project name
        self.name = None

        # The project directory
        self.directory = self._ensure_project_dir(directory)

        # Absolute path to where elements are loaded from within the project
        self.element_path = None

        # ProjectRefs for the main refs and also for junctions
        self.refs = ProjectRefs(self.directory, 'project.refs')
        self.junction_refs = ProjectRefs(self.directory, 'junction.refs')

        self.config = ProjectConfig()
        self.first_pass_config = ProjectConfig()

        self.junction = junction                 # The junction Element object, if this is a subproject
        self.fail_on_overlap = False             # Whether overlaps are treated as errors
        self.ref_storage = None                  # ProjectRefStorage setting
        self.base_environment = {}               # The base set of environment variables
        self.base_env_nocache = None             # The base nocache mask (list) for the environment

        #
        # Private Members
        #
        self._context = context  # The invocation Context
        self._aliases = {}       # Aliases dictionary

        self._cli_options = cli_options
        self._cache_key = None

        self._shell_command = []      # The default interactive shell command
        self._shell_environment = {}  # Statically set environment vars
        self._shell_host_files = []   # A list of HostMount objects

        self.artifact_cache_specs = None
        self._sandbox = None
        self._splits = None

        self._context.add_project(self)

        self._loaded = False

        profile_start(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-'))
        self._load(parent_loader=parent_loader, tempdir=tempdir)
        profile_end(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-'))

        self._loaded = True

    @property
    def plugins(self):
        return self.config.plugins

    @property
    def options(self):
        return self.config.options

    @property
    def base_variables(self):
        return self.config.base_variables

    @property
    def element_overrides(self):
        return self.config.element_overrides

    @property
    def source_overrides(self):
        return self.config.source_overrides

    def is_loaded(self):
        return self._loaded

    # translate_url():
    #
    # Translates the given url which may be specified with an alias
    # into a fully qualified url.
    #
    # Args:
    #    url (str): A url, which may be using an alias
    #
    # Returns:
    #    str: The fully qualified url, with aliases resolved
    #
    # This method is provided for :class:`.Source` objects to resolve
    # fully qualified urls based on the shorthand which is allowed
    # to be specified in the YAML
    def translate_url(self, url):
        if url and _ALIAS_SEPARATOR in url:
            url_alias, url_body = url.split(_ALIAS_SEPARATOR, 1)
            alias_url = self._aliases.get(url_alias)
            if alias_url:
                url = alias_url + url_body

        return url

    # get_shell_config()
    #
    # Gets the project specified shell configuration
    #
    # Returns:
    #    (list): The shell command
    #    (dict): The shell environment
    #    (list): The list of HostMount objects
    #
    def get_shell_config(self):
        return (self._shell_command, self._shell_environment, self._shell_host_files)

    # get_cache_key():
    #
    # Returns the cache key, calculating it if necessary
    #
    # Returns:
    #    (str): A hex digest cache key for the Context
    #
    def get_cache_key(self):
        if self._cache_key is None:

            # Anything that alters the build goes into the unique key
            # (currently nothing here)
            self._cache_key = _cachekey.generate_key({})

        return self._cache_key

    # load_elements()
    #
    # Loads elements from target names.
    #
    # Args:
    #    targets (list): Target names
    #    artifacts (ArtifactCache): Artifact cache
    #    rewritable (bool): Whether the loaded files should be rewritable
    #                       this is a bit more expensive due to deep copies
    #    fetch_subprojects (bool): Whether we should fetch subprojects as a part of the
    #                              loading process, if they are not yet locally cached
    #
    # Returns:
    #    (list): A list of loaded Element
    #
    def load_elements(self, targets, artifacts, *,
                      rewritable=False, fetch_subprojects=False):
        with self._context.timed_activity("Loading elements", silent_nested=True):
            meta_elements = self.loader.load(targets, rewritable=rewritable,
                                             ticker=None,
                                             fetch_subprojects=fetch_subprojects)

        with self._context.timed_activity("Resolving elements"):
            elements = [
                Element._new_from_meta(meta, artifacts)
                for meta in meta_elements
            ]

        # Now warn about any redundant source references which may have
        # been discovered in the resolve() phase.
        redundant_refs = Element._get_redundant_source_refs()
        if redundant_refs:
            detail = "The following inline specified source references will be ignored:\n\n"
            lines = [
                "{}:{}".format(source._get_provenance(), ref)
                for source, ref in redundant_refs
            ]
            detail += "\n".join(lines)
            self._context.message(
                Message(None, MessageType.WARN, "Ignoring redundant source references", detail=detail))

        return elements

    # cleanup()
    #
    # Cleans up resources used loading elements
    #
    def cleanup(self):
        self.loader.cleanup()

        # Reset the element loader state
        Element._reset_load_state()

    # _load():
    #
    # Loads the project configuration file in the project directory.
    #
    # Raises: LoadError if there was a problem with the project.conf
    #
    def _load(self, parent_loader=None, tempdir=None):

        # Load builtin default
        projectfile = os.path.join(self.directory, _PROJECT_CONF_FILE)
        config = _yaml.load(_site.default_project_config)

        # Load project local config and override the builtin
        try:
            project_conf = _yaml.load(projectfile)
        except LoadError as e:
            # Raise a more specific error here
            raise LoadError(LoadErrorReason.MISSING_PROJECT_CONF, str(e))

        _yaml.composite(config, project_conf)

        # Assert project's format version early, before validating toplevel keys
        format_version = _yaml.node_get(config, int, 'format-version')
        if BST_FORMAT_VERSION < format_version:
            major, minor = utils.get_bst_version()
            raise LoadError(
                LoadErrorReason.UNSUPPORTED_PROJECT,
                "Project requested format version {}, but BuildStream {}.{} only supports up until format version {}"
                .format(format_version, major, minor, BST_FORMAT_VERSION))

        # The project name, element path and option declarations
        # are constant and cannot be overridden by option conditional statements
        self.name = _yaml.node_get(config, str, 'name')

        # Validate that project name is a valid symbol name
        _yaml.assert_symbol_name(_yaml.node_get_provenance(config, 'name'),
                                 self.name, "project name")

        self.element_path = os.path.join(
            self.directory,
            _yaml.node_get(config, str, 'element-path')
        )

        self.config.options = OptionPool(self.element_path)
        self.first_pass_config.options = OptionPool(self.element_path)

        self.loader = Loader(self._context, self,
                             parent=parent_loader,
                             tempdir=tempdir)

        self._load_pass(_yaml.node_copy(config), self.first_pass_config, True)

        project_includes = Includes(self.loader)
        project_includes.process(config)

        self._load_pass(config, self.config, False)

        _yaml.node_validate(config, self.INCLUDE_CONFIG_KEYS + self.MAIN_FILE_CONFIG_KEYS)

        #
        # Now all YAML composition is done, from here on we just load
        # the values from our loaded configuration dictionary.
        #

        # Load artifacts pull/push configuration for this project
        self.artifact_cache_specs = ArtifactCache.specs_from_config_node(config)

        # Source url aliases
        self._aliases = _yaml.node_get(config, Mapping, 'aliases', default_value={})

        # Load sandbox environment variables
        self.base_environment = _yaml.node_get(config, Mapping, 'environment')
        self.base_env_nocache = _yaml.node_get(config, list, 'environment-nocache')

        # Load sandbox configuration
        self._sandbox = _yaml.node_get(config, Mapping, 'sandbox')

        # Load project split rules
        self._splits = _yaml.node_get(config, Mapping, 'split-rules')

        # Fail on overlap
        self.fail_on_overlap = _yaml.node_get(config, bool, 'fail-on-overlap')

        # Use separate file for storing source references
        self.ref_storage = _yaml.node_get(config, str, 'ref-storage')
        if self.ref_storage not in [ProjectRefStorage.INLINE, ProjectRefStorage.PROJECT_REFS]:
            p = _yaml.node_get_provenance(config, 'ref-storage')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Invalid value '{}' specified for ref-storage"
                            .format(p, self.ref_storage))

        # Load project.refs if it exists, this may be ignored.
        if self.ref_storage == ProjectRefStorage.PROJECT_REFS:
            self.refs.load(self.options)
            self.junction_refs.load(self.options)

        # Parse shell options
        shell_options = _yaml.node_get(config, Mapping, 'shell')
        _yaml.node_validate(shell_options, ['command', 'environment', 'host-files'])
        self._shell_command = _yaml.node_get(shell_options, list, 'command')

        # Perform environment expansion right away
        shell_environment = _yaml.node_get(shell_options, Mapping, 'environment', default_value={})
        for key, _ in _yaml.node_items(shell_environment):
            value = _yaml.node_get(shell_environment, str, key)
            self._shell_environment[key] = os.path.expandvars(value)

        # Host files is parsed as a list for convenience
        host_files = _yaml.node_get(shell_options, list, 'host-files', default_value=[])
        for host_file in host_files:
            if isinstance(host_file, str):
                mount = HostMount(host_file)
            else:
                # Some validation
                index = host_files.index(host_file)
                host_file_desc = _yaml.node_get(shell_options, Mapping, 'host-files', indices=[index])
                _yaml.node_validate(host_file_desc, ['path', 'host_path', 'optional'])

                # Parse the host mount
                path = _yaml.node_get(host_file_desc, str, 'path')
                host_path = _yaml.node_get(host_file_desc, str, 'host_path', default_value=None)
                optional = _yaml.node_get(host_file_desc, bool, 'optional', default_value=False)
                mount = HostMount(path, host_path, optional)

            self._shell_host_files.append(mount)

    # _load_pass():
    #
    # Loads parts of the project configuration that are different
    # for first and second pass configurations.
    #
    # Args:
    #    config (dict) - YaML node of the configuration file.
    #    output (ProjectConfig) - ProjectConfig to load configuration onto.
    #    ignore_unknown (bool) - Whether option loader shoud ignore unknown options.
    #
    def _load_pass(self, config, output, ignore_unknown):

        # Element and Source  type configurations will be composited later onto
        # element/source types, so we delete it from here and run our final
        # assertion after.
        output.element_overrides = _yaml.node_get(config, Mapping, 'elements', default_value={})
        output.source_overrides = _yaml.node_get(config, Mapping, 'sources', default_value={})
        config.pop('elements', None)
        config.pop('sources', None)
        _yaml.node_final_assertions(config)

        output.plugins = PluginCollection(self, self._context, self.directory, config)

        # Load project options
        options_node = _yaml.node_get(config, Mapping, 'options', default_value={})
        output.options.load(options_node)
        if self.junction:
            # load before user configuration
            output.options.load_yaml_values(self.junction.options, transform=self.junction._subst_string)

        # Collect option values specified in the user configuration
        overrides = self._context.get_overrides(self.name)
        override_options = _yaml.node_get(overrides, Mapping, 'options', default_value={})
        output.options.load_yaml_values(override_options)
        if self._cli_options:
            output.options.load_cli_values(self._cli_options, ignore_unknown=ignore_unknown)

        # We're done modifying options, now we can use them for substitutions
        output.options.resolve()

        #
        # Now resolve any conditionals in the remaining configuration,
        # any conditionals specified for project option declarations,
        # or conditionally specifying the project name; will be ignored.
        #
        output.options.process_node(config)

        # Load base variables
        output.base_variables = _yaml.node_get(config, Mapping, 'variables')

        # Add the project name as a default variable
        output.base_variables['project-name'] = self.name

        # Extend variables with automatic variables and option exports
        # Initialize it as a string as all variables are processed as strings.
        output.base_variables['max-jobs'] = str(multiprocessing.cpu_count())

        # Export options into variables, if that was requested
        output.options.export_variables(output.base_variables)

    # _ensure_project_dir()
    #
    # Returns path of the project directory, if a configuration file is found
    # in given directory or any of its parent directories.
    #
    # Args:
    #    directory (str) - directory from where the command was invoked
    #
    # Raises:
    #    LoadError if project.conf is not found
    #
    def _ensure_project_dir(self, directory):
        directory = os.path.abspath(directory)
        while not os.path.isfile(os.path.join(directory, _PROJECT_CONF_FILE)):
            parent_dir = os.path.dirname(directory)
            if directory == parent_dir:
                raise LoadError(
                    LoadErrorReason.MISSING_PROJECT_CONF,
                    '{} not found in current directory or any of its parent directories'
                    .format(_PROJECT_CONF_FILE))
            directory = parent_dir

        return directory
