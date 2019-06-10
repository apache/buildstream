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
import sys
from collections import OrderedDict
from pathlib import Path
from pluginbase import PluginBase
from . import utils
from . import _cachekey
from . import _site
from . import _yaml
from ._artifactelement import ArtifactElement
from ._profile import Topics, PROFILER
from ._exceptions import LoadError, LoadErrorReason
from ._options import OptionPool
from ._artifactcache import ArtifactCache
from ._sourcecache import SourceCache
from .sandbox import SandboxRemote
from ._elementfactory import ElementFactory
from ._sourcefactory import SourceFactory
from .types import CoreWarnings
from ._projectrefs import ProjectRefs, ProjectRefStorage
from ._versions import BST_FORMAT_VERSION
from ._loader import Loader
from .element import Element
from ._message import Message, MessageType
from ._includes import Includes
from ._platform import Platform
from ._workspaces import WORKSPACE_PROJECT_FILE


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
        self._aliases = None                     # Aliases dictionary


# Project()
#
# The Project Configuration
#
class Project():

    def __init__(self, directory, context, *, junction=None, cli_options=None,
                 default_mirror=None, parent_loader=None,
                 search_for_project=True, fetch_subprojects=None):

        # The project name
        self.name = None

        self._context = context  # The invocation Context, a private member

        if search_for_project:
            self.directory, self._invoked_from_workspace_element = self._find_project_dir(directory)
        else:
            self.directory = directory
            self._invoked_from_workspace_element = None

        self._absolute_directory_path = Path(self.directory).resolve()

        # Absolute path to where elements are loaded from within the project
        self.element_path = None

        # Default target elements
        self._default_targets = None

        # ProjectRefs for the main refs and also for junctions
        self.refs = ProjectRefs(self.directory, 'project.refs')
        self.junction_refs = ProjectRefs(self.directory, 'junction.refs')

        self.config = ProjectConfig()
        self.first_pass_config = ProjectConfig()

        self.junction = junction                 # The junction Element object, if this is a subproject

        self.ref_storage = None                  # ProjectRefStorage setting
        self.base_environment = {}               # The base set of environment variables
        self.base_env_nocache = None             # The base nocache mask (list) for the environment

        #
        # Private Members
        #

        self._default_mirror = default_mirror    # The name of the preferred mirror.

        self._cli_options = cli_options
        self._cache_key = None

        self._fatal_warnings = []             # A list of warnings which should trigger an error

        self._shell_command = []      # The default interactive shell command
        self._shell_environment = {}  # Statically set environment vars
        self._shell_host_files = []   # A list of HostMount objects

        self.artifact_cache_specs = None
        self.source_cache_specs = None
        self.remote_execution_specs = None
        self._sandbox = None
        self._splits = None

        self._context.add_project(self)

        self._partially_loaded = False
        self._fully_loaded = False
        self._project_includes = None

        with PROFILER.profile(Topics.LOAD_PROJECT, self.directory.replace(os.sep, '-')):
            self._load(parent_loader=parent_loader, fetch_subprojects=fetch_subprojects)

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
            alias_url = config._aliases.get_str(url_alias, default=None)
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
            self._cache_key = _cachekey.generate_key(_yaml.new_empty_node())

        return self._cache_key

    # get_path_from_node()
    #
    # Fetches the project path from a dictionary node and validates it
    #
    # Paths are asserted to never lead to a directory outside of the project
    # directory. In addition, paths can not point to symbolic links, fifos,
    # sockets and block/character devices.
    #
    # The `check_is_file` and `check_is_dir` parameters can be used to
    # perform additional validations on the path. Note that an exception
    # will always be raised if both parameters are set to ``True``.
    #
    # Args:
    #    node (dict): A dictionary loaded from YAML
    #    key (str): The key whose value contains a path to validate
    #    check_is_file (bool): If ``True`` an error will also be raised
    #                          if path does not point to a regular file.
    #                          Defaults to ``False``
    #    check_is_dir (bool): If ``True`` an error will be also raised
    #                         if path does not point to a directory.
    #                         Defaults to ``False``
    # Returns:
    #    (str): The project path
    #
    # Raises:
    #    (LoadError): In case that the project path is not valid or does not
    #                 exist
    #
    def get_path_from_node(self, node, key, *,
                           check_is_file=False, check_is_dir=False):
        path_str = node.get_str(key)
        path = Path(path_str)
        full_path = self._absolute_directory_path / path

        provenance = _yaml.node_get_provenance(node, key=key)

        if full_path.is_symlink():
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                            "{}: Specified path '{}' must not point to "
                            "symbolic links "
                            .format(provenance, path_str))

        if path.parts and path.parts[0] == '..':
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID,
                            "{}: Specified path '{}' first component must "
                            "not be '..'"
                            .format(provenance, path_str))

        try:
            if sys.version_info[0] == 3 and sys.version_info[1] < 6:
                full_resolved_path = full_path.resolve()
            else:
                full_resolved_path = full_path.resolve(strict=True)  # pylint: disable=unexpected-keyword-arg
        except FileNotFoundError:
            raise LoadError(LoadErrorReason.MISSING_FILE,
                            "{}: Specified path '{}' does not exist"
                            .format(provenance, path_str))

        is_inside = self._absolute_directory_path in full_resolved_path.parents or (
            full_resolved_path == self._absolute_directory_path)

        if not is_inside:
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID,
                            "{}: Specified path '{}' must not lead outside of the "
                            "project directory"
                            .format(provenance, path_str))

        if path.is_absolute():
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID,
                            "{}: Absolute path: '{}' invalid.\n"
                            "Please specify a path relative to the project's root."
                            .format(provenance, path))

        if full_resolved_path.is_socket() or (
                full_resolved_path.is_fifo() or
                full_resolved_path.is_block_device()):
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                            "{}: Specified path '{}' points to an unsupported "
                            "file kind"
                            .format(provenance, path_str))

        if check_is_file and not full_resolved_path.is_file():
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                            "{}: Specified path '{}' is not a regular file"
                            .format(provenance, path_str))

        if check_is_dir and not full_resolved_path.is_dir():
            raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                            "{}: Specified path '{}' is not a directory"
                            .format(provenance, path_str))

        return path_str

    def _validate_node(self, node):
        _yaml.node_validate(node, [
            'format-version',
            'element-path', 'variables',
            'environment', 'environment-nocache',
            'split-rules', 'elements', 'plugins',
            'aliases', 'name', 'defaults',
            'artifacts', 'options',
            'fail-on-overlap', 'shell', 'fatal-warnings',
            'ref-storage', 'sandbox', 'mirrors', 'remote-execution',
            'sources', 'source-caches', '(@)'
        ])

    # create_element()
    #
    # Instantiate and return an element
    #
    # Args:
    #    meta (MetaElement): The loaded MetaElement
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns:
    #    (Element): A newly created Element object of the appropriate kind
    #
    def create_element(self, meta, *, first_pass=False):
        if first_pass:
            return self.first_pass_config.element_factory.create(self._context, self, meta)
        else:
            return self.config.element_factory.create(self._context, self, meta)

    # create_artifact_element()
    #
    # Instantiate and return an ArtifactElement
    #
    # Args:
    #    ref (str): A string of the artifact ref
    #
    # Returns:
    #    (ArtifactElement): A newly created ArtifactElement object of the appropriate kind
    #
    def create_artifact_element(self, ref):
        return ArtifactElement(self._context, ref)

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

        return config._aliases.get_str(alias, default=None)

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

        if not alias or alias not in config._aliases:  # pylint: disable=unsupported-membership-test
            return [None]

        mirror_list = []
        for key, alias_mapping in config.mirrors.items():
            if alias in alias_mapping:
                if key == config.default_mirror:
                    mirror_list = alias_mapping[alias] + mirror_list
                else:
                    mirror_list += alias_mapping[alias]
        mirror_list.append(config._aliases.get_str(alias))
        return mirror_list

    # load_elements()
    #
    # Loads elements from target names.
    #
    # Args:
    #    targets (list): Target names
    #    rewritable (bool): Whether the loaded files should be rewritable
    #                       this is a bit more expensive due to deep copies
    #
    # Returns:
    #    (list): A list of loaded Element
    #
    def load_elements(self, targets, *, rewritable=False):
        with self._context.messenger.timed_activity("Loading elements", silent_nested=True):
            meta_elements = self.loader.load(targets, rewritable=rewritable, ticker=None)

        with self._context.messenger.timed_activity("Resolving elements"):
            elements = [
                Element._new_from_meta(meta)
                for meta in meta_elements
            ]

        Element._clear_meta_elements_cache()

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
            self._context.messenger.message(
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

    # invoked_from_workspace_element()
    #
    # Returns the element whose workspace was used to invoke buildstream
    # if buildstream was invoked from an external workspace
    #
    def invoked_from_workspace_element(self):
        return self._invoked_from_workspace_element

    # cleanup()
    #
    # Cleans up resources used loading elements
    #
    def cleanup(self):
        # Reset the element loader state
        Element._reset_load_state()

    # get_default_target()
    #
    # Attempts to interpret which element the user intended to run a command on.
    # This is for commands that only accept a single target element and thus,
    # this only uses the workspace element (if invoked from workspace directory)
    # and does not use the project default targets.
    #
    def get_default_target(self):
        return self._invoked_from_workspace_element

    # get_default_targets()
    #
    # Attempts to interpret which elements the user intended to run a command on.
    # This is for commands that accept multiple target elements.
    #
    def get_default_targets(self):

        # If _invoked_from_workspace_element has a value,
        # a workspace element was found before a project config
        # Therefore the workspace does not contain a project
        if self._invoked_from_workspace_element:
            return (self._invoked_from_workspace_element,)

        # Default targets from project configuration
        if self._default_targets:
            return tuple(self._default_targets)

        # If default targets are not configured, default to all project elements
        default_targets = []
        for root, dirs, files in os.walk(self.element_path):
            # Do not recurse down the ".bst" directory which is where we stage
            # junctions and other BuildStream internals.
            if ".bst" in dirs:
                dirs.remove(".bst")
            for file in files:
                if file.endswith(".bst"):
                    rel_dir = os.path.relpath(root, self.element_path)
                    rel_file = os.path.join(rel_dir, file).lstrip("./")
                    default_targets.append(rel_file)

        return tuple(default_targets)

    # _load():
    #
    # Loads the project configuration file in the project
    # directory process the first pass.
    #
    # Raises: LoadError if there was a problem with the project.conf
    #
    def _load(self, *, parent_loader=None, fetch_subprojects):

        # Load builtin default
        projectfile = os.path.join(self.directory, _PROJECT_CONF_FILE)
        self._default_config_node = _yaml.load(_site.default_project_config)

        # Load project local config and override the builtin
        try:
            self._project_conf = _yaml.load(projectfile)
        except LoadError as e:
            # Raise a more specific error here
            if e.reason == LoadErrorReason.MISSING_FILE:
                raise LoadError(LoadErrorReason.MISSING_PROJECT_CONF, str(e)) from e
            else:
                raise

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

        self._validate_node(pre_config_node)

        # The project name, element path and option declarations
        # are constant and cannot be overridden by option conditional statements
        self.name = self._project_conf.get_str('name')

        # Validate that project name is a valid symbol name
        _yaml.assert_symbol_name(_yaml.node_get_provenance(pre_config_node, 'name'),
                                 self.name, "project name")

        self.element_path = os.path.join(
            self.directory,
            self.get_path_from_node(pre_config_node, 'element-path',
                                    check_is_dir=True)
        )

        self.config.options = OptionPool(self.element_path)
        self.first_pass_config.options = OptionPool(self.element_path)

        defaults = pre_config_node.get_mapping('defaults')
        _yaml.node_validate(defaults, ['targets'])
        self._default_targets = _yaml.node_get(defaults, list, "targets")

        # Fatal warnings
        self._fatal_warnings = _yaml.node_get(pre_config_node, list, 'fatal-warnings', default_value=[])

        self.loader = Loader(self._context, self,
                             parent=parent_loader, fetch_subprojects=fetch_subprojects)

        self._project_includes = Includes(self.loader, copy_tree=False)

        project_conf_first_pass = _yaml.node_copy(self._project_conf)
        self._project_includes.process(project_conf_first_pass, only_local=True)
        config_no_include = _yaml.node_copy(self._default_config_node)
        _yaml.composite(config_no_include, project_conf_first_pass)

        self._load_pass(config_no_include, self.first_pass_config,
                        ignore_unknown=True)

        # Use separate file for storing source references
        self.ref_storage = pre_config_node.get_str('ref-storage')
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

        self._validate_node(config)

        #
        # Now all YAML composition is done, from here on we just load
        # the values from our loaded configuration dictionary.
        #

        # Load artifacts pull/push configuration for this project
        project_specs = ArtifactCache.specs_from_config_node(config, self.directory)
        override_specs = ArtifactCache.specs_from_config_node(
            self._context.get_overrides(self.name), self.directory)

        self.artifact_cache_specs = override_specs + project_specs

        if self.junction:
            parent = self.junction._get_project()
            self.artifact_cache_specs = parent.artifact_cache_specs + self.artifact_cache_specs

        # Load source caches with pull/push config
        self.source_cache_specs = SourceCache.specs_from_config_node(config, self.directory)

        # Load remote-execution configuration for this project
        project_specs = SandboxRemote.specs_from_config_node(config, self.directory)
        override_specs = SandboxRemote.specs_from_config_node(
            self._context.get_overrides(self.name), self.directory)

        if override_specs is not None:
            self.remote_execution_specs = override_specs
        elif project_specs is not None:
            self.remote_execution_specs = project_specs
        else:
            self.remote_execution_specs = self._context.remote_execution_specs

        # Load sandbox environment variables
        self.base_environment = config.get_mapping('environment')
        self.base_env_nocache = _yaml.node_get(config, list, 'environment-nocache')

        # Load sandbox configuration
        self._sandbox = config.get_mapping('sandbox')

        # Load project split rules
        self._splits = config.get_mapping('split-rules')

        # Support backwards compatibility for fail-on-overlap
        fail_on_overlap = config.get_scalar('fail-on-overlap', None)

        # Deprecation check
        if not fail_on_overlap.is_none():
            self._context.messenger.message(
                Message(
                    None,
                    MessageType.WARN,
                    "Use of fail-on-overlap within project.conf " +
                    "is deprecated. Consider using fatal-warnings instead."
                )
            )

            if (CoreWarnings.OVERLAPS not in self._fatal_warnings) and fail_on_overlap.as_bool():
                self._fatal_warnings.append(CoreWarnings.OVERLAPS)

        # Load project.refs if it exists, this may be ignored.
        if self.ref_storage == ProjectRefStorage.PROJECT_REFS:
            self.refs.load(self.options)

        # Parse shell options
        shell_options = config.get_mapping('shell')
        _yaml.node_validate(shell_options, ['command', 'environment', 'host-files'])
        self._shell_command = _yaml.node_get(shell_options, list, 'command')

        # Perform environment expansion right away
        shell_environment = shell_options.get_mapping('environment', default={})
        for key in _yaml.node_keys(shell_environment):
            value = shell_environment.get_str(key)
            self._shell_environment[key] = os.path.expandvars(value)

        # Host files is parsed as a list for convenience
        host_files = _yaml.node_get(shell_options, list, 'host-files', default_value=[])
        for host_file in host_files:
            if isinstance(host_file, str):
                mount = HostMount(host_file)
            else:
                # Some validation
                index = host_files.index(host_file)
                host_file_desc = _yaml.node_get(shell_options, dict, 'host-files', indices=[index])
                _yaml.node_validate(host_file_desc, ['path', 'host_path', 'optional'])

                # Parse the host mount
                path = host_file_desc.get_str('path')
                host_path = host_file_desc.get_str('host_path', default=None)
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
        output.element_overrides = config.get_mapping('elements', default={})
        output.source_overrides = config.get_mapping('sources', default={})
        _yaml.node_del(config, 'elements', safe=True)
        _yaml.node_del(config, 'sources', safe=True)
        _yaml.node_final_assertions(config)

        self._load_plugin_factories(config, output)

        # Load project options
        options_node = config.get_mapping('options', default={})
        output.options.load(options_node)
        if self.junction:
            # load before user configuration
            output.options.load_yaml_values(self.junction.options, transform=self.junction._subst_string)

        # Collect option values specified in the user configuration
        overrides = self._context.get_overrides(self.name)
        override_options = overrides.get_mapping('options', default={})
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
        output.base_variables = config.get_mapping('variables')

        # Add the project name as a default variable
        _yaml.node_set(output.base_variables, 'project-name', self.name)

        # Extend variables with automatic variables and option exports
        # Initialize it as a string as all variables are processed as strings.
        # Based on some testing (mainly on AWS), maximum effective
        # max-jobs value seems to be around 8-10 if we have enough cores
        # users should set values based on workload and build infrastructure
        platform = Platform.get_platform()
        _yaml.node_set(output.base_variables, 'max-jobs', str(platform.get_cpu_count(8)))

        # Export options into variables, if that was requested
        output.options.export_variables(output.base_variables)

        # Override default_mirror if not set by command-line
        output.default_mirror = self._default_mirror or overrides.get_str(
            'default-mirror', default=None)

        mirrors = _yaml.node_get(config, list, 'mirrors', default_value=[])
        for mirror in mirrors:
            allowed_mirror_fields = [
                'name', 'aliases'
            ]
            _yaml.node_validate(mirror, allowed_mirror_fields)
            mirror_name = mirror.get_str('name')
            alias_mappings = {}
            for alias_mapping, uris in _yaml.node_items(mirror.get_mapping('aliases')):
                assert isinstance(uris, list)
                alias_mappings[alias_mapping] = list(uris)
            output.mirrors[mirror_name] = alias_mappings
            if not output.default_mirror:
                output.default_mirror = mirror_name

        # Source url aliases
        output._aliases = config.get_mapping('aliases', default={})

    # _find_project_dir()
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
    # Returns:
    #    (str) - the directory that contains the project, and
    #    (str) - the name of the element required to find the project, or None
    #
    def _find_project_dir(self, directory):
        workspace_element = None
        config_filenames = [_PROJECT_CONF_FILE, WORKSPACE_PROJECT_FILE]
        found_directory, filename = utils._search_upward_for_files(
            directory, config_filenames
        )
        if filename == _PROJECT_CONF_FILE:
            project_directory = found_directory
        elif filename == WORKSPACE_PROJECT_FILE:
            workspace_project_cache = self._context.get_workspace_project_cache()
            workspace_project = workspace_project_cache.get(found_directory)
            if workspace_project:
                project_directory = workspace_project.get_default_project_path()
                workspace_element = workspace_project.get_default_element()
        else:
            raise LoadError(
                LoadErrorReason.MISSING_PROJECT_CONF,
                "None of {names} found in '{path}' or any of its parent directories"
                .format(names=config_filenames, path=directory))

        return project_directory, workspace_element

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

            origin_value = origin.get_str('origin')
            if origin_value not in allowed_origins:
                raise LoadError(
                    LoadErrorReason.INVALID_YAML,
                    "Origin '{}' is not one of the allowed types"
                    .format(origin_value))

            # Store source versions for checking later
            source_versions = origin.get_mapping('sources', default={})
            for key in _yaml.node_keys(source_versions):
                if key in source_format_versions:
                    raise LoadError(
                        LoadErrorReason.INVALID_YAML,
                        "Duplicate listing of source '{}'".format(key))
                source_format_versions[key] = _yaml.node_get(source_versions, int, key)

            # Store element versions for checking later
            element_versions = origin.get_mapping('elements', default={})
            for key in _yaml.node_keys(element_versions):
                if key in element_format_versions:
                    raise LoadError(
                        LoadErrorReason.INVALID_YAML,
                        "Duplicate listing of element '{}'".format(key))
                element_format_versions[key] = _yaml.node_get(element_versions, int, key)

            # Store the origins if they're not 'core'.
            # core elements are loaded by default, so storing is unnecessary.
            if origin.get_str('origin') != 'core':
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
    #    origin (node) - a node indicating the origin of a group of
    #                    plugins.
    #    plugin_group (str) - The name of the type of plugin that is being
    #                         loaded
    #    destination (list) - A list of nodes to store the origins in
    #
    # Raises:
    #    LoadError if 'origin' is an unexpected value
    def _store_origin(self, origin, plugin_group, destination):
        expected_groups = ['sources', 'elements']
        if plugin_group not in expected_groups:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "Unexpected plugin group: {}, expecting {}"
                            .format(plugin_group, expected_groups))
        node_keys = [key for key in _yaml.node_keys(origin)]
        if plugin_group in node_keys:
            origin_node = _yaml.node_copy(origin)
            plugins = origin.get_mapping(plugin_group, default={})
            _yaml.node_set(origin_node, 'plugins', [k for k in _yaml.node_keys(plugins)])
            for group in expected_groups:
                if group in origin_node:
                    _yaml.node_del(origin_node, group)

            if origin_node.get_str('origin') == 'local':
                path = self.get_path_from_node(origin, 'path',
                                               check_is_dir=True)
                # paths are passed in relative to the project, but must be absolute
                _yaml.node_set(origin_node, 'path', os.path.join(self.directory, path))
            destination.append(origin_node)

    # _warning_is_fatal():
    #
    # Returns true if the warning in question should be considered fatal based on
    # the project configuration.
    #
    # Args:
    #   warning_str (str): The warning configuration string to check against
    #
    # Returns:
    #    (bool): True if the warning should be considered fatal and cause an error.
    #
    def _warning_is_fatal(self, warning_str):
        return warning_str in self._fatal_warnings
