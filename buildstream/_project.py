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
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

import os
from collections import Mapping, OrderedDict
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
from .element import Element
from ._message import Message, MessageType
from ._includes import Includes


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


# Represents project configuration that can have different values for junctions.
class ProjectConfig:
    def __init__(self):
        self.element_factory = None
        self.source_factory = None
        self.options = None                      # OptionPool
        self.base_variables = {}                 # The base set of variables
        self.element_overrides = {}              # Element specific configurations
        self.source_overrides = {}               # Source specific configurations
        self.mirrors = OrderedDict()             # contains dicts of alias-mappings to URIs.
        self.default_mirror = None               # The name of the preferred mirror.
        self._aliases = {}                       # Aliases dictionary


# Project()
#
# The Project Configuration
#
class Project():

    def __init__(self, directory, context, *, junction=None, cli_options=None,
                 default_mirror=None, parent_loader=None, tempdir=None):

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

        self._default_mirror = default_mirror    # The name of the preferred mirror.

        self._cli_options = cli_options
        self._cache_key = None

        self._shell_command = []      # The default interactive shell command
        self._shell_environment = {}  # Statically set environment vars
        self._shell_host_files = []   # A list of HostMount objects

        self.artifact_cache_specs = None
        self._sandbox = None
        self._splits = None

        self._context.add_project(self)

        self._partially_loaded = False
        self._fully_loaded = False
        self._project_includes = None

        profile_start(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-'))
        self._load(parent_loader=parent_loader, tempdir=tempdir)
        profile_end(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-'))

        self._partially_loaded = True

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

    # translate_url():
    #
    # Translates the given url which may be specified with an alias
    # into a fully qualified url.
    #
    # Args:
    #    url (str): A url, which may be using an alias
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns:
    #    str: The fully qualified url, with aliases resolved
    #
    # This method is provided for :class:`.Source` objects to resolve
    # fully qualified urls based on the shorthand which is allowed
    # to be specified in the YAML
    def translate_url(self, url, *, first_pass=False):
        if first_pass:
            config = self.first_pass_config
        else:
            config = self.config

        if url and utils._ALIAS_SEPARATOR in url:
            url_alias, url_body = url.split(utils._ALIAS_SEPARATOR, 1)
            alias_url = config._aliases.get(url_alias)
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

    # create_element()
    #
    # Instantiate and return an element
    #
    # Args:
    #    artifacts (ArtifactCache): The artifact cache
    #    meta (MetaElement): The loaded MetaElement
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns:
    #    (Element): A newly created Element object of the appropriate kind
    #
    def create_element(self, artifacts, meta, *, first_pass=False):
        if first_pass:
            return self.first_pass_config.element_factory.create(self._context, self, artifacts, meta)
        else:
            return self.config.element_factory.create(self._context, self, artifacts, meta)

    # create_source()
    #
    # Instantiate and return a Source
    #
    # Args:
    #    meta (MetaSource): The loaded MetaSource
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns:
    #    (Source): A newly created Source object of the appropriate kind
    #
    def create_source(self, meta, *, first_pass=False):
        if first_pass:
            return self.first_pass_config.source_factory.create(self._context, self, meta)
        else:
            return self.config.source_factory.create(self._context, self, meta)

    # get_alias_uri()
    #
    # Returns the URI for a given alias, if it exists
    #
    # Args:
    #    alias (str): The alias.
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns:
    #    str: The URI for the given alias; or None: if there is no URI for
    #         that alias.
    def get_alias_uri(self, alias, *, first_pass=False):
        if first_pass:
            config = self.first_pass_config
        else:
            config = self.config

        return config._aliases.get(alias)

    # get_alias_uris()
    #
    # Args:
    #    alias (str): The alias.
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns a list of every URI to replace an alias with
    def get_alias_uris(self, alias, *, first_pass=False):
        if first_pass:
            config = self.first_pass_config
        else:
            config = self.config

        if not alias or alias not in config._aliases:
            return [None]

        mirror_list = []
        for key, alias_mapping in config.mirrors.items():
            if alias in alias_mapping:
                if key == config.default_mirror:
                    mirror_list = alias_mapping[alias] + mirror_list
                else:
                    mirror_list += alias_mapping[alias]
        mirror_list.append(config._aliases[alias])
        return mirror_list

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

    # ensure_fully_loaded()
    #
    # Ensure project has finished loading. At first initialization, a
    # project can only load junction elements. Other elements require
    # project to be fully loaded.
    #
    def ensure_fully_loaded(self):
        if self._fully_loaded:
            return
        assert self._partially_loaded
        self._fully_loaded = True

        if self.junction:
            self.junction._get_project().ensure_fully_loaded()

        self._load_second_pass()

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
    # Loads the project configuration file in the project
    # directory process the first pass.
    #
    # Raises: LoadError if there was a problem with the project.conf
    #
    def _load(self, parent_loader=None, tempdir=None):

        # Load builtin default
        projectfile = os.path.join(self.directory, _PROJECT_CONF_FILE)
        self._default_config_node = _yaml.load(_site.default_project_config)

        # Load project local config and override the builtin
        try:
            self._project_conf = _yaml.load(projectfile)
        except LoadError as e:
            # Raise a more specific error here
            raise LoadError(LoadErrorReason.MISSING_PROJECT_CONF, str(e))

        pre_config_node = _yaml.node_copy(self._default_config_node)
        _yaml.composite(pre_config_node, self._project_conf)

        # Assert project's format version early, before validating toplevel keys
        format_version = _yaml.node_get(pre_config_node, int, 'format-version')
        if BST_FORMAT_VERSION < format_version:
            major, minor = utils.get_bst_version()
            raise LoadError(
                LoadErrorReason.UNSUPPORTED_PROJECT,
                "Project requested format version {}, but BuildStream {}.{} only supports up until format version {}"
                .format(format_version, major, minor, BST_FORMAT_VERSION))

        # FIXME:
        #
        #   Performing this check manually in the absense
        #   of proper support from _yaml.node_get(), this should
        #   be removed in favor of a proper accessor function
        #   from the _yaml module when #591 is fixed.
        #
        if self._project_conf.get('name') is None:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: project.conf does not contain expected key '{}'".format(projectfile, 'name'))

        # The project name, element path and option declarations
        # are constant and cannot be overridden by option conditional statements
        self.name = _yaml.node_get(pre_config_node, str, 'name')

        # Validate that project name is a valid symbol name
        _yaml.assert_symbol_name(_yaml.node_get_provenance(pre_config_node, 'name'),
                                 self.name, "project name")

        self.element_path = os.path.join(
            self.directory,
            _yaml.node_get_project_path(pre_config_node, 'element-path', self.directory,
                                        check_is_dir=True)
        )

        self.config.options = OptionPool(self.element_path)
        self.first_pass_config.options = OptionPool(self.element_path)

        self.loader = Loader(self._context, self,
                             parent=parent_loader,
                             tempdir=tempdir)

        self._project_includes = Includes(self.loader, copy_tree=False)

        project_conf_first_pass = _yaml.node_copy(self._project_conf)
        self._project_includes.process(project_conf_first_pass, only_local=True)
        config_no_include = _yaml.node_copy(self._default_config_node)
        _yaml.composite(config_no_include, project_conf_first_pass)

        self._load_pass(config_no_include, self.first_pass_config,
                        ignore_unknown=True)

        # Use separate file for storing source references
        self.ref_storage = _yaml.node_get(pre_config_node, str, 'ref-storage')
        if self.ref_storage not in [ProjectRefStorage.INLINE, ProjectRefStorage.PROJECT_REFS]:
            p = _yaml.node_get_provenance(pre_config_node, 'ref-storage')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Invalid value '{}' specified for ref-storage"
                            .format(p, self.ref_storage))

        if self.ref_storage == ProjectRefStorage.PROJECT_REFS:
            self.junction_refs.load(self.first_pass_config.options)

    # _load_second_pass()
    #
    # Process the second pass of loading the project configuration.
    #
    def _load_second_pass(self):
        project_conf_second_pass = _yaml.node_copy(self._project_conf)
        self._project_includes.process(project_conf_second_pass)
        config = _yaml.node_copy(self._default_config_node)
        _yaml.composite(config, project_conf_second_pass)

        self._load_pass(config, self.config)

        _yaml.node_validate(config, [
            'format-version',
            'element-path', 'variables',
            'environment', 'environment-nocache',
            'split-rules', 'elements', 'plugins',
            'aliases', 'name',
            'artifacts', 'options',
            'fail-on-overlap', 'shell',
            'ref-storage', 'sandbox', 'mirrors'
        ])

        #
        # Now all YAML composition is done, from here on we just load
        # the values from our loaded configuration dictionary.
        #

        # Load artifacts pull/push configuration for this project
        self.artifact_cache_specs = ArtifactCache.specs_from_config_node(config, self.directory)

        # Load sandbox environment variables
        self.base_environment = _yaml.node_get(config, Mapping, 'environment')
        self.base_env_nocache = _yaml.node_get(config, list, 'environment-nocache')

        # Load sandbox configuration
        self._sandbox = _yaml.node_get(config, Mapping, 'sandbox')

        # Load project split rules
        self._splits = _yaml.node_get(config, Mapping, 'split-rules')

        # Fail on overlap
        self.fail_on_overlap = _yaml.node_get(config, bool, 'fail-on-overlap')

        # Load project.refs if it exists, this may be ignored.
        if self.ref_storage == ProjectRefStorage.PROJECT_REFS:
            self.refs.load(self.options)

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
    def _load_pass(self, config, output, *,
                   ignore_unknown=False):

        # Element and Source  type configurations will be composited later onto
        # element/source types, so we delete it from here and run our final
        # assertion after.
        output.element_overrides = _yaml.node_get(config, Mapping, 'elements', default_value={})
        output.source_overrides = _yaml.node_get(config, Mapping, 'sources', default_value={})
        config.pop('elements', None)
        config.pop('sources', None)
        _yaml.node_final_assertions(config)

        self._load_plugin_factories(config, output)

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
        # Don't forget to also resolve options in the element and source overrides.
        output.options.process_node(config)
        output.options.process_node(output.element_overrides)
        output.options.process_node(output.source_overrides)

        # Load base variables
        output.base_variables = _yaml.node_get(config, Mapping, 'variables')

        # Add the project name as a default variable
        output.base_variables['project-name'] = self.name

        # Extend variables with automatic variables and option exports
        # Initialize it as a string as all variables are processed as strings.
        # Based on some testing (mainly on AWS), maximum effective
        # max-jobs value seems to be around 8-10 if we have enough cores
        # users should set values based on workload and build infrastructure
        output.base_variables['max-jobs'] = str(min(len(os.sched_getaffinity(0)), 8))

        # Export options into variables, if that was requested
        output.options.export_variables(output.base_variables)

        # Override default_mirror if not set by command-line
        output.default_mirror = self._default_mirror or _yaml.node_get(overrides, str,
                                                                       'default-mirror', default_value=None)

        mirrors = _yaml.node_get(config, list, 'mirrors', default_value=[])
        for mirror in mirrors:
            allowed_mirror_fields = [
                'name', 'aliases'
            ]
            _yaml.node_validate(mirror, allowed_mirror_fields)
            mirror_name = _yaml.node_get(mirror, str, 'name')
            alias_mappings = {}
            for alias_mapping, uris in _yaml.node_items(mirror['aliases']):
                assert isinstance(uris, list)
                alias_mappings[alias_mapping] = list(uris)
            output.mirrors[mirror_name] = alias_mappings
            if not output.default_mirror:
                output.default_mirror = mirror_name

        # Source url aliases
        output._aliases = _yaml.node_get(config, Mapping, 'aliases', default_value={})

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

    def _load_plugin_factories(self, config, output):
        plugin_source_origins = []   # Origins of custom sources
        plugin_element_origins = []  # Origins of custom elements

        # Plugin origins and versions
        origins = _yaml.node_get(config, list, 'plugins', default_value=[])
        source_format_versions = {}
        element_format_versions = {}
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
                if key in source_format_versions:
                    raise LoadError(
                        LoadErrorReason.INVALID_YAML,
                        "Duplicate listing of source '{}'".format(key))
                source_format_versions[key] = _yaml.node_get(source_versions, int, key)

            # Store element versions for checking later
            element_versions = _yaml.node_get(origin, Mapping, 'elements', default_value={})
            for key, _ in _yaml.node_items(element_versions):
                if key in element_format_versions:
                    raise LoadError(
                        LoadErrorReason.INVALID_YAML,
                        "Duplicate listing of element '{}'".format(key))
                element_format_versions[key] = _yaml.node_get(element_versions, int, key)

            # Store the origins if they're not 'core'.
            # core elements are loaded by default, so storing is unnecessary.
            if _yaml.node_get(origin, str, 'origin') != 'core':
                self._store_origin(origin, 'sources', plugin_source_origins)
                self._store_origin(origin, 'elements', plugin_element_origins)

        pluginbase = PluginBase(package='buildstream.plugins')
        output.element_factory = ElementFactory(pluginbase,
                                                plugin_origins=plugin_element_origins,
                                                format_versions=element_format_versions)
        output.source_factory = SourceFactory(pluginbase,
                                              plugin_origins=plugin_source_origins,
                                              format_versions=source_format_versions)

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
                path = _yaml.node_get_project_path(origin, 'path',
                                                   self.directory,
                                                   check_is_dir=True)
                # paths are passed in relative to the project, but must be absolute
                origin_dict['path'] = os.path.join(self.directory, path)
            destination.append(origin_dict)
