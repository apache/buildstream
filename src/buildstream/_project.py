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
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

from typing import TYPE_CHECKING, Optional, Dict, Union, List

import os
import urllib.parse
from pathlib import Path
from pluginbase import PluginBase
from . import utils
from . import _site
from . import _yaml
from ._variables import Variables
from .utils import UtilError
from ._profile import Topics, PROFILER
from ._exceptions import LoadError
from .exceptions import LoadErrorReason
from ._options import OptionPool
from .node import ScalarNode, MappingNode, ProvenanceInformation, _assert_symbol_name
from ._pluginfactory import ElementFactory, SourceFactory, load_plugin_origin
from .types import CoreWarnings, _HostMount, _SourceMirror, _SourceUriPolicy
from ._projectrefs import ProjectRefs, ProjectRefStorage
from ._loader import Loader, LoadContext
from .element import Element
from ._includes import Includes
from ._workspaces import WORKSPACE_PROJECT_FILE
from ._remotespec import RemoteSpec


if TYPE_CHECKING:
    from ._context import Context


# Project Configuration file
_PROJECT_CONF_FILE = "project.conf"


# Represents project configuration that can have different values for junctions.
class ProjectConfig:
    def __init__(self):
        self.options = None  # OptionPool
        self.base_variables = {}  # The base set of variables
        self.element_overrides = {}  # Element specific configurations
        self.source_overrides = {}  # Source specific configurations
        self.mirrors = {}  # Dictionary of _SourceAlias objects
        self.default_mirror = None  # The name of the preferred mirror.
        self._aliases = None  # Aliases dictionary


# Project()
#
# The Project Configuration
#
# Args:
#    directory: The project directory, or None for dummy ArtifactProjects
#    context: The invocation context
#    junction: The junction Element causing this project to be loaded
#    cli_options: The project options specified on the command line
#    default_mirror: The default mirror specified on the command line
#    parent_loader: The parent loader
#    provenance_node: The YAML provenance causing this project to be loaded
#    search_for_project: Whether to search for a project directory, e.g. from workspace metadata or parent directories
#
class Project:
    def __init__(
        self,
        directory: Optional[str],
        context: "Context",
        *,
        junction: Optional[object] = None,
        cli_options: Optional[Dict[str, str]] = None,
        default_mirror: Optional[str] = None,
        parent_loader: Optional[Loader] = None,
        provenance_node: Optional[ProvenanceInformation] = None,
        search_for_project: bool = True,
    ):
        #
        # Public members
        #
        self.name: str = ""  # The project name
        self.directory: Optional[str] = directory  # The project directory
        self.element_path: Optional[str] = None  # The project relative element path

        self.load_context: LoadContext  # The LoadContext
        self.loader: Optional[Loader] = None  # The loader associated to this project
        self.junction: Optional[object] = junction  # The junction Element object, if this is a subproject

        self.ref_storage: Optional[ProjectRefStorage] = None  # Where to store source refs
        self.refs: Optional[ProjectRefs] = None
        self.junction_refs: Optional[ProjectRefs] = None

        self.config: ProjectConfig = ProjectConfig()
        self.first_pass_config: ProjectConfig = ProjectConfig()

        self.base_environment: Union[MappingNode, Dict[str, str]] = {}  # The base set of environment variables
        self.base_env_nocache: List[str] = []  # The base nocache mask (list) for the environment

        # Remote specs for communicating with remote services
        self.artifact_cache_specs: List[RemoteSpec] = []  # Artifact caches
        self.source_cache_specs: List[RemoteSpec] = []  # Source caches

        self.element_factory: Optional[ElementFactory] = None  # ElementFactory for loading elements
        self.source_factory: Optional[SourceFactory] = None  # SourceFactory for loading sources

        self.sandbox: Optional[MappingNode] = None
        self.splits: Optional[MappingNode] = None

        #
        # Private members
        #
        self._context: "Context" = context  # The invocation Context
        self._invoked_from_workspace_element: Optional[str] = None
        self._absolute_directory_path: Optional[Path] = None

        self._default_targets: Optional[List[str]] = None  # Default target elements
        self._default_mirror: Optional[str] = default_mirror  # The name of the preferred mirror.
        self._cli_options: Optional[Dict[str, str]] = cli_options

        self._fatal_warnings: List[str] = []  # A list of warnings which should trigger an error
        self._shell_command: List[str] = []  # The default interactive shell command
        self._shell_environment: Dict[str, str] = {}  # Statically set environment vars
        self._shell_host_files: List[_HostMount] = []  # A list of HostMount objects
        self._mirror_override: bool = False  # Whether mirrors have been declared in user configuration

        # This is a lookup table of lists indexed by project,
        # the child dictionaries are lists of ScalarNodes indicating
        # junction names
        self._junction_duplicates: Dict[str, List[str]] = {}

        # A list of project relative junctions to consider as 'internal',
        # stored as ScalarNodes.
        self._junction_internal: List[str] = []

        self._partially_loaded: bool = False
        self._fully_loaded: bool = False
        self._project_includes: Optional[Includes] = None

        #
        # Initialization body
        #
        if parent_loader:
            self.load_context = parent_loader.load_context
        else:
            self.load_context = LoadContext(self._context)

        if search_for_project:
            self.directory, self._invoked_from_workspace_element = self._find_project_dir(directory)

        if self.directory:
            self._absolute_directory_path = Path(self.directory).resolve()
            self.refs = ProjectRefs(self.directory, "project.refs")
            self.junction_refs = ProjectRefs(self.directory, "junction.refs")

        self._context.add_project(self)

        if self.directory:
            with PROFILER.profile(Topics.LOAD_PROJECT, self.directory.replace(os.sep, "-")):
                self._load(parent_loader=parent_loader, provenance_node=provenance_node)
        else:
            self._fully_loaded = True

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

    ########################################################
    #                     Public Methods                   #
    ########################################################

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
    #    (list): The list of _HostMount objects
    #
    def get_shell_config(self):
        return (self._shell_command, self._shell_environment, self._shell_host_files)

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
    #    node (ScalarNode): A Node loaded from YAML containing the path to validate
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
    def get_path_from_node(self, node, *, check_is_file=False, check_is_dir=False):
        path_str = node.as_str()
        path = Path(path_str)
        full_path = self._absolute_directory_path / path

        if full_path.is_symlink():
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' must not point to " "symbolic links ".format(provenance, path_str),
                LoadErrorReason.PROJ_PATH_INVALID_KIND,
            )

        if path.parts and path.parts[0] == "..":
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' first component must " "not be '..'".format(provenance, path_str),
                LoadErrorReason.PROJ_PATH_INVALID,
            )

        try:
            full_resolved_path = full_path.resolve(strict=True)
        except FileNotFoundError:
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' does not exist".format(provenance, path_str), LoadErrorReason.MISSING_FILE
            )

        is_inside = self._absolute_directory_path in full_resolved_path.parents or (
            full_resolved_path == self._absolute_directory_path
        )

        if not is_inside:
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' must not lead outside of the "
                "project directory".format(provenance, path_str),
                LoadErrorReason.PROJ_PATH_INVALID,
            )

        if path.is_absolute():
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Absolute path: '{}' invalid.\n"
                "Please specify a path relative to the project's root.".format(provenance, path),
                LoadErrorReason.PROJ_PATH_INVALID,
            )

        if full_resolved_path.is_socket() or (full_resolved_path.is_fifo() or full_resolved_path.is_block_device()):
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' points to an unsupported " "file kind".format(provenance, path_str),
                LoadErrorReason.PROJ_PATH_INVALID_KIND,
            )

        if check_is_file and not full_resolved_path.is_file():
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' is not a regular file".format(provenance, path_str),
                LoadErrorReason.PROJ_PATH_INVALID_KIND,
            )

        if check_is_dir and not full_resolved_path.is_dir():
            provenance = node.get_provenance()
            raise LoadError(
                "{}: Specified path '{}' is not a directory".format(provenance, path_str),
                LoadErrorReason.PROJ_PATH_INVALID_KIND,
            )

        return path_str

    # create_element()
    #
    # Instantiate and return an element
    #
    # Args:
    #    load_element (LoadElement): The LoadElement
    #
    # Returns:
    #    (Element): A newly created Element object of the appropriate kind
    #
    def create_element(self, load_element):
        return self.element_factory.create(self._context, self, load_element)

    # create_source()
    #
    # Instantiate and return a Source
    #
    # Args:
    #    meta (MetaSource): The loaded MetaSource
    #    variables (Variables): The list of variables available to the source
    #
    # Returns:
    #    (Source): A newly created Source object of the appropriate kind
    #
    def create_source(self, meta, variables):
        return self.source_factory.create(self._context, self, meta, variables)

    # alias_exists()
    #
    # Returns the URI for a given alias, if it exists
    #
    # Args:
    #    alias (str): The alias.
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #
    # Returns:
    #    bool: Whether the alias is declared in the scope of this project
    #
    def alias_exists(self, alias, *, first_pass=False):
        if first_pass:
            config = self.first_pass_config
        else:
            config = self.config

        return config._aliases.get_str(alias, default=None) is not None

    # get_alias_uris()
    #
    # Args:
    #    alias (str): The alias.
    #    first_pass (bool): Whether to use first pass configuration (for junctions)
    #    tracking (bool): Whether we want the aliases for tracking (otherwise assume fetching)
    #
    # Returns a list of every URI to replace an alias with
    def get_alias_uris(self, alias, *, first_pass=False, tracking=False):
        if first_pass:
            config = self.first_pass_config
        else:
            config = self.config

        if not alias or alias not in config._aliases:  # pylint: disable=unsupported-membership-test
            return [None]

        uri_list = []
        policy = self._context.track_source if tracking else self._context.fetch_source

        if policy in (_SourceUriPolicy.ALL, _SourceUriPolicy.MIRRORS) or (
            policy == _SourceUriPolicy.USER and self._mirror_override
        ):
            for mirror_name, mirror in config.mirrors.items():
                if alias in mirror.aliases:
                    if mirror_name == config.default_mirror:
                        uri_list = mirror.aliases[alias] + uri_list
                    else:
                        uri_list += mirror.aliases[alias]

        if policy in (_SourceUriPolicy.ALL, _SourceUriPolicy.ALIASES):
            uri_list.append(config._aliases.get_str(alias))

        return uri_list

    # load_elements()
    #
    # Loads elements from target names.
    #
    # Args:
    #    targets (list): Target names
    #
    # Returns:
    #    (list): A list of loaded Element
    #
    def load_elements(self, targets):

        with self._context.messenger.simple_task("Loading elements", silent_nested=True) as task:
            self.load_context.set_task(task)
            load_elements = self.loader.load(targets)
            self.load_context.set_task(None)

        with self._context.messenger.simple_task("Resolving elements", silent_nested=True) as task:
            if task:
                task.set_maximum_progress(self.loader.loaded)
            elements = [Element._new_from_load_element(load_element, task) for load_element in load_elements]

        Element._clear_meta_elements_cache()

        # Assert loaders after resolving everything, this is because plugin
        # loading (across junction boundaries) can also be the cause of
        # conflicting projects.
        #
        self.load_context.assert_loaders()

        # Now warn about any redundant source references which may have
        # been discovered in the resolve() phase.
        redundant_refs = Element._get_redundant_source_refs()
        if redundant_refs:
            detail = "The following inline specified source references will be ignored:\n\n"
            lines = ["{}:{}".format(source._get_provenance(), ref) for source, ref in redundant_refs]
            detail += "\n".join(lines)
            self._context.messenger.warn("Ignoring redundant source references", detail=detail)

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

        # Here we mark the project as fully loaded right away,
        # before doing the work.
        #
        # This function will otherwise reenter itself infinitely:
        #
        #   * Ensuring the invariant that a parent project is fully
        #     loaded before completing the load of this project, will
        #     trigger this function when completing the load of subprojects.
        #
        #   * Completing the load of this project may include processing
        #     some `(@)` include directives, which can directly trigger
        #     the loading of subprojects.
        #
        self._fully_loaded = True

        if self.junction:
            self.junction._get_project().ensure_fully_loaded()

        self._load_second_pass()

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

    # junction_is_duplicated()
    #
    # Check whether this loader is specified as a duplicate by
    # this project.
    #
    # Args:
    #    project_name: (str): The project name
    #    loader (Loader): The loader to check for
    #
    # Returns:
    #    (bool): Whether the loader is specified as duplicate
    #
    def junction_is_duplicated(self, project_name, loader):

        junctions = self._junction_duplicates.get(project_name, {})

        # Iterate over all paths specified by this project and see
        # if we find a match for the specified loader.
        #
        # Using the regular `Loader.get_loader()` codepath from this
        # project ensures that we will find the correct loader relative
        # to this project, regardless of any overrides or link elements
        # which might have been used in the project.
        #
        for dup_path in junctions:
            search = self.loader.get_loader(dup_path.as_str(), dup_path, load_subprojects=False)
            if loader is search:
                return True

        return False

    # junction_is_internal()
    #
    # Check whether this loader is specified as internal to
    # this project.
    #
    # Args:
    #    loader (Loader): The loader to check for
    #
    # Returns:
    #    (bool): Whether the loader is specified as internal
    #
    def junction_is_internal(self, loader):

        # Iterate over all paths specified by this project and see
        # if we find a match for the specified loader.
        #
        # Using the regular `Loader.get_loader()` codepath from this
        # project ensures that we will find the correct loader relative
        # to this project, regardless of any overrides or link elements
        # which might have been used in the project.
        #
        for internal_path in self._junction_internal:
            search = self.loader.get_loader(internal_path.as_str(), internal_path, load_subprojects=False)
            if loader is search:
                return True

        return False

    # loaded_projects()
    #
    # A generator which yields all the projects in context of a loaded
    # pipeline, including the self project.
    #
    # Projects will be yielded in the order in which they were loaded
    # for the current session's pipeline.
    #
    # This is used by the frontend to print information about all the
    # loaded projects.
    #
    # Yields:
    #    (_ProjectInformation): A descriptive project information object
    #
    def loaded_projects(self):
        yield from self.load_context.loaded_projects()

    ########################################################
    #                    Private Methods                   #
    ########################################################

    # _validate_toplevel_node()
    #
    # Validates the toplevel project.conf keys
    #
    # Args:
    #    node (MappingNode): The toplevel project.conf node
    #    first_pass (bool): Whether this is the first or second pass
    #
    def _validate_toplevel_node(self, node, *, first_pass=False):
        node.validate_keys(
            [
                "min-version",
                "element-path",
                "variables",
                "environment",
                "environment-nocache",
                "split-rules",
                "elements",
                "plugins",
                "aliases",
                "name",
                "defaults",
                "artifacts",
                "options",
                "fail-on-overlap",
                "shell",
                "fatal-warnings",
                "ref-storage",
                "sandbox",
                "mirrors",
                "sources",
                "source-caches",
                "junctions",
                "(@)",
                "(?)",
            ]
        )

        # Keys which are invalid if specified outside of project.conf
        if not first_pass:
            invalid_keys = {"name", "element-path", "min-version", "plugins"}

            for invalid_key in invalid_keys:
                invalid_node = node.get_node(invalid_key, allow_none=True)
                if invalid_node:
                    provenance = invalid_node.get_provenance()
                    if (
                        provenance._shortname != "project.conf"
                        and provenance._filename != _site.default_project_config
                    ):
                        raise LoadError(
                            "{}: Unexpected key: {}".format(provenance, invalid_key),
                            LoadErrorReason.INVALID_DATA,
                            detail="The '{}' configuration must be specified in project.conf".format(invalid_key),
                        )

    # _validate_version()
    #
    # Asserts that we have a BuildStream installation which is recent
    # enough for the project required version
    #
    # Args:
    #    config_node (dict) - YaML node of the configuration file.
    #
    # Raises: LoadError if there was a problem with the project.conf
    #
    def _validate_version(self, config_node):

        bst_major, bst_minor = utils._get_bst_api_version()

        # Use a custom error message for the absence of the required "min-version"
        # as this may be an indication that we are trying to load a BuildStream 1 project.
        #
        min_version_node = config_node.get_scalar("min-version", None)
        if min_version_node.is_none():
            p = config_node.get_provenance()
            raise LoadError(
                "{}: Dictionary did not contain expected key 'min-version'".format(p),
                LoadErrorReason.INVALID_DATA,
                #
                # TODO: Provide a link to documentation on how to install
                #       BuildStream 1 in a venv
                #
                detail="If you are trying to use a BuildStream 1 project, "
                + "please install BuildStream 1 to use this project.",
            )

        # Parse the project declared minimum required BuildStream version
        min_version = min_version_node.as_str()
        try:
            min_version_major, min_version_minor = utils._parse_version(min_version)
        except UtilError as e:
            p = min_version_node.get_provenance()
            raise LoadError(
                "{}: {}\n".format(p, e),
                LoadErrorReason.INVALID_DATA,
                detail="The min-version must be specified as MAJOR.MINOR with "
                + "numeric major and minor minimum required version numbers",
            ) from e

        # Future proofing, in case there is ever a BuildStream 3
        if min_version_major != bst_major:
            p = min_version_node.get_provenance()
            raise LoadError(
                "{}: Version mismatch".format(p),
                LoadErrorReason.UNSUPPORTED_PROJECT,
                detail="Project requires BuildStream {}, ".format(min_version_major)
                + "but BuildStream {} is installed.\n".format(bst_major)
                + "Please use BuildStream {} with this project.".format(min_version_major),
            )

        # Check minimal minor point requirement is satisfied
        if min_version_minor > bst_minor:
            p = min_version_node.get_provenance()
            raise LoadError(
                "{}: Version mismatch".format(p),
                LoadErrorReason.UNSUPPORTED_PROJECT,
                detail="Project requires at least BuildStream {}.{}, ".format(min_version_major, min_version_minor)
                + "but BuildStream {}.{} is installed.\n".format(bst_major, bst_minor)
                + "Please upgrade BuildStream.",
            )

    # _load():
    #
    # Loads the project configuration file in the project
    # directory process the first pass.
    #
    # Raises: LoadError if there was a problem with the project.conf
    #
    def _load(self, *, parent_loader=None, provenance_node=None):

        # Load builtin default
        projectfile = os.path.join(self.directory, _PROJECT_CONF_FILE)
        self._default_config_node = _yaml.load(_site.default_project_config, shortname="projectconfig.yaml")

        # Load project local config and override the builtin
        try:
            self._project_conf = _yaml.load(projectfile, shortname=_PROJECT_CONF_FILE, project=self)
        except LoadError as e:
            # Raise a more specific error here
            if e.reason == LoadErrorReason.MISSING_FILE:
                raise LoadError(str(e), LoadErrorReason.MISSING_PROJECT_CONF) from e

            # Otherwise re-raise the original exception
            raise

        pre_config_node = self._default_config_node.clone()
        self._project_conf._composite(pre_config_node)

        # Assert project's minimum required version early, before validating toplevel keys
        self._validate_version(pre_config_node)

        self._validate_toplevel_node(pre_config_node, first_pass=True)

        # The project name, element path and option declarations
        # are constant and cannot be overridden by option conditional statements
        # FIXME: we should be keeping node information for further composition here
        self.name = self._project_conf.get_str("name")

        # Validate that project name is a valid symbol name
        _assert_symbol_name(self.name, "project name", ref_node=pre_config_node.get_node("name"))

        self.element_path = os.path.join(
            self.directory, self.get_path_from_node(pre_config_node.get_scalar("element-path"), check_is_dir=True)
        )

        self.config.options = OptionPool(self.element_path)
        self.first_pass_config.options = OptionPool(self.element_path)

        defaults = pre_config_node.get_mapping("defaults")
        defaults.validate_keys(["targets"])
        self._default_targets = defaults.get_str_list("targets")

        # Fatal warnings
        self._fatal_warnings = pre_config_node.get_str_list("fatal-warnings", default=[])

        # Junction configuration
        junctions_node = pre_config_node.get_mapping("junctions", default={})
        junctions_node.validate_keys(["duplicates", "internal"])

        # Parse duplicates
        junction_duplicates = junctions_node.get_mapping("duplicates", default={})
        for project_name, junctions in junction_duplicates.items():
            self._junction_duplicates[project_name] = junctions

        # Parse internal
        self._junction_internal = junctions_node.get_sequence("internal", default=[])

        self.loader = Loader(self, parent=parent_loader, provenance_node=provenance_node)

        self._project_includes = Includes(self.loader, copy_tree=False)

        project_conf_first_pass = self._project_conf.clone()
        self._project_includes.process(project_conf_first_pass, only_local=True, process_project_options=False)
        config_no_include = self._default_config_node.clone()
        project_conf_first_pass._composite(config_no_include)

        # Plugin factories must be defined in project.conf, not included from elsewhere.
        self._load_plugin_factories(config_no_include)

        self._load_pass(config_no_include, self.first_pass_config, ignore_unknown=True)

        # Use separate file for storing source references
        ref_storage_node = pre_config_node.get_scalar("ref-storage")
        self.ref_storage = ref_storage_node.as_str()
        if self.ref_storage not in [ProjectRefStorage.INLINE, ProjectRefStorage.PROJECT_REFS]:
            p = ref_storage_node.get_provenance()
            raise LoadError(
                "{}: Invalid value '{}' specified for ref-storage".format(p, self.ref_storage),
                LoadErrorReason.INVALID_DATA,
            )

        if self.ref_storage == ProjectRefStorage.PROJECT_REFS:
            self.junction_refs.load(self.first_pass_config.options)

    # _load_second_pass()
    #
    # Process the second pass of loading the project configuration.
    #
    def _load_second_pass(self):
        project_conf_second_pass = self._project_conf.clone()
        self._project_includes.process(project_conf_second_pass, process_project_options=False)
        config = self._default_config_node.clone()
        project_conf_second_pass._composite(config)

        self._load_pass(config, self.config)

        self._validate_toplevel_node(config, first_pass=False)

        #
        # Now all YAML composition is done, from here on we just load
        # the values from our loaded configuration dictionary.
        #

        # Load artifact remote specs
        caches = config.get_sequence("artifacts", default=[], allowed_types=[MappingNode])
        for node in caches:
            spec = RemoteSpec.new_from_node(node, self.directory)
            self.artifact_cache_specs.append(spec)

        # Load source cache remote specs
        caches = config.get_sequence("source-caches", default=[], allowed_types=[MappingNode])
        for node in caches:
            spec = RemoteSpec.new_from_node(node, self.directory)
            self.source_cache_specs.append(spec)

        # Load sandbox environment variables
        self.base_environment = config.get_mapping("environment")
        self.base_env_nocache = config.get_str_list("environment-nocache")

        # Load sandbox configuration
        self.sandbox = config.get_mapping("sandbox")

        # Load project split rules
        self.splits = config.get_mapping("split-rules")

        # Support backwards compatibility for fail-on-overlap
        fail_on_overlap = config.get_scalar("fail-on-overlap", None)

        # Deprecation check
        if not fail_on_overlap.is_none():
            self._context.messenger.warn(
                "Use of fail-on-overlap within project.conf "
                + "is deprecated. Consider using fatal-warnings instead.",
            )

            if (CoreWarnings.OVERLAPS not in self._fatal_warnings) and fail_on_overlap.as_bool():
                self._fatal_warnings.append(CoreWarnings.OVERLAPS)

        # Load project.refs if it exists, this may be ignored.
        if self.ref_storage == ProjectRefStorage.PROJECT_REFS:
            self.refs.load(self.options)

        # Parse shell options
        shell_options = config.get_mapping("shell")
        shell_options.validate_keys(["command", "environment", "host-files"])
        self._shell_command = shell_options.get_str_list("command")

        # Perform environment expansion right away
        shell_environment = shell_options.get_mapping("environment", default={})
        for key in shell_environment.keys():
            value = shell_environment.get_str(key)
            self._shell_environment[key] = os.path.expandvars(value)

        # Host files is parsed as a list for convenience
        host_files = shell_options.get_sequence("host-files", default=[])
        for host_file in host_files:
            if isinstance(host_file, ScalarNode):
                mount = _HostMount(host_file.as_str())
            else:
                # Some validation
                host_file.validate_keys(["path", "host_path", "optional"])

                # Parse the host mount
                path = host_file.get_str("path")
                host_path = host_file.get_str("host_path", default=None)
                optional = host_file.get_bool("optional", default=False)
                mount = _HostMount(path, host_path, optional)

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
    def _load_pass(self, config, output, *, ignore_unknown=False):

        # Load project options
        options_node = config.get_mapping("options", default={})
        output.options.load(options_node)
        if self.junction:
            # load before user configuration
            output.options.load_yaml_values(self.junction.options)

        # Collect option values specified in the user configuration
        overrides = self._context.get_overrides(self.name)
        override_options = overrides.get_mapping("options", default={})
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
        # Specify any options that would be ignored in the restrict list
        # so as to raise an appropriate error.
        #
        output.options.process_node(
            config,
            restricted=[
                "min-version",
                "name",
                "element-path",
                "junctions",
                "defaults",
                "fatal-warnings",
                "ref-storage",
                "options",
                "plugins",
            ],
        )

        # Element and Source  type configurations will be composited later onto
        # element/source types, so we delete it from here and run our final
        # assertion after.
        output.element_overrides = config.get_mapping("elements", default={})
        output.source_overrides = config.get_mapping("sources", default={})
        config.safe_del("elements")
        config.safe_del("sources")
        config._assert_fully_composited()

        # Load base variables
        output.base_variables = config.get_mapping("variables")

        # Add the project name as a default variable
        output.base_variables["project-name"] = self.name

        # Extend variables with automatic variables and option exports
        # Initialize it as a string as all variables are processed as strings.
        # Based on some testing (mainly on AWS), maximum effective
        # max-jobs value seems to be around 8-10 if we have enough cores
        # users should set values based on workload and build infrastructure
        if self._context.build_max_jobs == 0:
            # User requested automatic max-jobs
            platform = self._context.platform
            output.base_variables["max-jobs"] = str(platform.get_cpu_count(8))
        else:
            # User requested explicit max-jobs setting
            output.base_variables["max-jobs"] = str(self._context.build_max_jobs)

        # Export options into variables, if that was requested
        output.options.export_variables(output.base_variables)

        # Prepare a Variables instance for substitution of source alias and
        # source mirror values.
        #
        # This allows substitution of any project-level variables, plus the special
        # variables which allow resolving project relative directories on the host.
        #
        toplevel_project = self._context.get_toplevel_project()
        variables_node = output.base_variables.clone()
        variables_node["project-root"] = str(self._absolute_directory_path)
        variables_node["toplevel-root"] = str(toplevel_project._absolute_directory_path)
        variables_node["project-root-uri"] = "file://" + urllib.parse.quote(str(self._absolute_directory_path))
        variables_node["toplevel-root-uri"] = "file://" + urllib.parse.quote(
            str(toplevel_project._absolute_directory_path)
        )
        variables = Variables(variables_node)

        # Override default_mirror if not set by command-line
        output.default_mirror = self._default_mirror or overrides.get_str("default-mirror", default=None)

        # First try mirrors specified in user configuration, user configuration
        # is allowed to completely disable mirrors by specifying an empty list,
        # so we check for a None value here too.
        #
        mirrors_node = overrides.get_sequence("mirrors", default=None)
        if mirrors_node is None:
            mirrors_node = config.get_sequence("mirrors", default=[])
        else:
            self._mirror_override = True

        # Perform variable substitutions in source mirror definitions,
        # even if the mirrors are specified in user configuration.
        variables.expand(mirrors_node)

        # Collect _SourceMirror objects
        for mirror_node in mirrors_node:
            mirror = _SourceMirror.new_from_node(mirror_node)
            output.mirrors[mirror.name] = mirror
            if not output.default_mirror:
                output.default_mirror = mirror.name

        # Source url aliases
        output._aliases = config.get_mapping("aliases", default={})

        # Perform variable substitutions in source aliases
        variables.expand(output._aliases)

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
        found_directory, filename = utils._search_upward_for_files(directory, config_filenames)
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
                "None of {names} found in '{path}' or any of its parent directories".format(
                    names=config_filenames, path=directory
                ),
                LoadErrorReason.MISSING_PROJECT_CONF,
            )

        return project_directory, workspace_element

    # _load_plugin_factories()
    #
    # Loads the plugin factories
    #
    # Args:
    #    config (MappingNode): The main project.conf node in the first pass
    #
    def _load_plugin_factories(self, config):
        # Create the factories
        pluginbase = PluginBase(package="buildstream.plugins")
        self.element_factory = ElementFactory(pluginbase)
        self.source_factory = SourceFactory(pluginbase)

        # Load the plugin origins and register them to their factories
        origins = config.get_sequence("plugins", default=[])
        for origin_node in origins:
            origin = load_plugin_origin(self, origin_node)
            for kind, conf in origin.elements.items():
                self.element_factory.register_plugin_origin(kind, origin, conf.allow_deprecated)
            for kind, conf in origin.sources.items():
                self.source_factory.register_plugin_origin(kind, origin, conf.allow_deprecated)

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
