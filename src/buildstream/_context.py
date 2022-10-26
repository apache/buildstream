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

from typing import TYPE_CHECKING, List, Dict, Set, Optional, Iterable

import os
import shutil
from . import utils
from . import _site
from . import _yaml
from ._exceptions import LoadError
from .exceptions import LoadErrorReason
from ._messenger import Messenger
from ._profile import Topics, PROFILER
from ._platform import Platform
from ._artifactcache import ArtifactCache
from ._elementsourcescache import ElementSourcesCache
from ._remotespec import RemoteSpec, RemoteExecutionSpec
from ._sourcecache import SourceCache
from ._cas import CASCache, CASLogLevel
from .types import _CacheBuildTrees, _PipelineSelection, _SchedulerErrorAction, _SourceUriPolicy
from ._workspaces import Workspaces, WorkspaceProjectCache
from .node import Node, MappingNode


if TYPE_CHECKING:
    # pylint: disable=cyclic-import
    from ._project import Project

    # pylint: enable=cyclic-import


# _CacheConfig
#
# A convenience object for parsing artifact/source cache configurations
#
class _CacheConfig:
    def __init__(self, override_projects: bool, remote_specs: List[RemoteSpec]):
        self.override_projects: bool = override_projects
        self.remote_specs: List[RemoteSpec] = remote_specs

    @classmethod
    def new_from_node(cls, node: MappingNode) -> "_CacheConfig":
        node.validate_keys(["override-project-caches", "servers"])
        servers = node.get_sequence("servers", default=[], allowed_types=[MappingNode])

        override_projects: bool = node.get_bool("push", default=False)
        remote_specs: List[RemoteSpec] = [RemoteSpec.new_from_node(node) for node in servers]

        return cls(override_projects, remote_specs)


# Context()
#
# The Context object holds all of the user preferences
# and context for a given invocation of BuildStream.
#
# This is a collection of data from configuration files and command
# line arguments and consists of information such as where to store
# logs and artifacts, where to perform builds and cache downloaded sources,
# verbosity levels and basically anything pertaining to the context
# in which BuildStream was invoked.
#
class Context:
    def __init__(self, *, use_casd: bool = True) -> None:

        # Whether we are running as part of a test suite. This is only relevant
        # for developing BuildStream itself.
        self.is_running_in_test_suite: bool = "BST_TEST_SUITE" in os.environ

        # Filename indicating which configuration file was used, or None for the defaults
        self.config_origin: Optional[str] = None

        # The directory under which other directories are based
        self.cachedir: Optional[str] = None

        # The directory where various sources are stored
        self.sourcedir: Optional[str] = None

        # The directory where build sandboxes will be created
        self.builddir: Optional[str] = None

        # The directory for CAS
        self.casdir: Optional[str] = None

        # Whether to use casd - meant for interfaces such as
        # completion where casd is not required
        self.use_casd: bool = use_casd

        # Whether we are going to build, this is required for some conditional
        # functionality to take place only in the case that we are building.
        self.build: bool = False

        # The directory for artifact protos
        self.artifactdir: Optional[str] = None

        # The directory for temporary files
        self.tmpdir: Optional[str] = None

        # Default root location for workspaces
        self.workspacedir: Optional[str] = None

        # The global remote execution configuration
        self.remote_execution_specs: Optional[RemoteExecutionSpec] = None

        # The configured artifact cache remote specs for each project
        self.project_artifact_cache_specs: Dict[str, List[RemoteSpec]] = {}

        # The configured source cache remote specs for each project
        self.project_source_cache_specs: Dict[str, List[RemoteSpec]] = {}

        # The directory to store build logs
        self.logdir: Optional[str] = None

        # The abbreviated cache key length to display in the UI
        self.log_key_length: Optional[int] = None

        # Whether debug mode is enabled
        self.log_debug: Optional[int] = None

        # Whether verbose mode is enabled
        self.log_verbose: Optional[int] = None

        # Maximum number of lines to print from build logs
        self.log_error_lines: Optional[int] = None

        # Maximum number of lines to print in the master log for a detailed message
        self.log_message_lines: Optional[int] = None

        # Format string for printing the pipeline at startup time
        self.log_element_format: Optional[str] = None

        # Format string for printing message lines in the master log
        self.log_message_format: Optional[str] = None

        # Wether to rate limit the updating of the bst output where applicable
        self.log_throttle_updates: Optional[int] = None

        # Maximum number of fetch or refresh tasks
        self.sched_fetchers: Optional[int] = None

        # Maximum number of build tasks
        self.sched_builders: Optional[int] = None

        # Maximum number of push tasks
        self.sched_pushers: Optional[int] = None

        # Maximum number of retries for network tasks
        self.sched_network_retries: Optional[int] = None

        # What to do when a build fails in non interactive mode
        self.sched_error_action: Optional[str] = None

        # Maximum jobs per build
        self.build_max_jobs: Optional[int] = None

        # Control which dependencies to build
        self.build_dependencies: Optional[_PipelineSelection] = None

        # Control which URIs can be accessed when fetching sources
        self.fetch_source: Optional[str] = None

        # Control which URIs can be accessed when tracking sources
        self.track_source: Optional[str] = None

        # Size of the artifact cache in bytes
        self.config_cache_quota: Optional[int] = None

        # User specified cache quota, used for display messages
        self.config_cache_quota_string: Optional[str] = None

        # Remote cache server
        self.remote_cache_spec: Optional[RemoteSpec] = None

        # Whether or not to attempt to pull build trees globally
        self.pull_buildtrees: Optional[bool] = None

        # Whether or not to cache build trees on artifact creation
        self.cache_buildtrees: Optional[str] = None

        # Don't shoot the messenger
        self.messenger: Messenger = Messenger()

        # Make sure the XDG vars are set in the environment before loading anything
        self._init_xdg()

        #
        # Private variables
        #

        # Whether elements must be rebuilt when their dependencies have changed
        self._strict_build_plan: Optional[bool] = None

        # Lists of globally configured cache configurations
        self._global_artifact_cache_config: _CacheConfig = _CacheConfig(False, [])
        self._global_source_cache_config: _CacheConfig = _CacheConfig(False, [])

        # Set of all actively configured remote specs
        self._active_artifact_cache_specs: Set[RemoteSpec] = set()
        self._active_source_cache_specs: Set[RemoteSpec] = set()

        self._platform: Optional[Platform] = None
        self._artifactcache: Optional[ArtifactCache] = None
        self._elementsourcescache: Optional[ElementSourcesCache] = None
        self._sourcecache: Optional[SourceCache] = None
        self._projects: List["Project"] = []
        self._project_overrides: MappingNode = Node.from_dict({})
        self._workspaces: Optional[Workspaces] = None
        self._workspace_project_cache: WorkspaceProjectCache = WorkspaceProjectCache()
        self._cascache: Optional[CASCache] = None

    # __enter__()
    #
    # Called when entering the with-statement context.
    #
    def __enter__(self) -> "Context":
        return self

    # __exit__()
    #
    # Called when exiting the with-statement context.
    #
    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._artifactcache:
            self._artifactcache.release_resources()

        if self._elementsourcescache:
            self._elementsourcescache.release_resources()

        if self._sourcecache:
            self._sourcecache.release_resources()

        if self._cascache:
            self._cascache.release_resources(self.messenger)

    # load()
    #
    # Loads the configuration files
    #
    # Args:
    #    config: The user specified configuration file, if any
    #
    # Raises:
    #   LoadError
    #
    # This will first load the BuildStream default configuration and then
    # override that configuration with the configuration file indicated
    # by *config*, if any was specified.
    #
    @PROFILER.profile(Topics.LOAD_CONTEXT, "load")
    def load(self, config: Optional[str] = None) -> None:
        # If a specific config file is not specified, default to trying
        # a $XDG_CONFIG_HOME/buildstream.conf file
        #
        if not config:
            #
            # Support parallel installations of BuildStream by first
            # trying a (major point) version specific configuration file
            # and then falling back to buildstream.conf.
            #
            for config_filename in ("buildstream2.conf", "buildstream.conf"):
                default_config = os.path.join(os.environ["XDG_CONFIG_HOME"], config_filename)
                if os.path.exists(default_config):
                    config = default_config
                    break

        # Load default config
        #
        defaults = _yaml.load(_site.default_user_config, shortname="userconfig.yaml")

        if config:
            self.config_origin = os.path.abspath(config)

            # Here we use the fullpath as the shortname as well, as it is useful to have
            # a fullpath displayed in errors for the user configuration
            user_config = _yaml.load(config, shortname=config)
            user_config._composite(defaults)

        # Give obsoletion warnings
        if "builddir" in defaults:
            raise LoadError("builddir is obsolete, use cachedir", LoadErrorReason.INVALID_DATA)

        if "artifactdir" in defaults:
            raise LoadError("artifactdir is obsolete", LoadErrorReason.INVALID_DATA)

        defaults.validate_keys(
            [
                "cachedir",
                "sourcedir",
                "builddir",
                "logdir",
                "scheduler",
                "build",
                "fetch",
                "track",
                "artifacts",
                "source-caches",
                "logging",
                "projects",
                "cache",
                "workspacedir",
                "remote-execution",
            ]
        )

        for directory in ["cachedir", "sourcedir", "logdir", "workspacedir"]:
            # Allow the ~ tilde expansion and any environment variables in
            # path specification in the config files.
            #
            path = defaults.get_str(directory)
            path = os.path.expanduser(path)
            path = os.path.expandvars(path)
            path = os.path.normpath(path)
            setattr(self, directory, path)

            # Relative paths don't make sense in user configuration. The exception is
            # workspacedir where `.` is useful as it will be combined with the name
            # specified on the command line.
            if not os.path.isabs(path) and not (directory == "workspacedir" and path == "."):
                raise LoadError("{} must be an absolute path".format(directory), LoadErrorReason.INVALID_DATA)

        # add directories not set by users
        assert self.cachedir
        self.tmpdir = os.path.join(self.cachedir, "tmp")
        self.casdir = os.path.join(self.cachedir, "cas")
        self.builddir = os.path.join(self.cachedir, "build")
        self.artifactdir = os.path.join(self.cachedir, "artifacts", "refs")

        # Move old artifact cas to cas if it exists and create symlink
        old_casdir = os.path.join(self.cachedir, "artifacts", "cas")
        if os.path.exists(old_casdir) and not os.path.islink(old_casdir) and not os.path.exists(self.casdir):
            os.rename(old_casdir, self.casdir)
            os.symlink(self.casdir, old_casdir)

        # Cleanup old extract directories
        old_extractdir = os.path.join(self.cachedir, "extract")
        if os.path.isdir(old_extractdir):
            shutil.rmtree(old_extractdir, ignore_errors=True)

        # Load quota configuration
        # We need to find the first existing directory in the path of our
        # casdir - the casdir may not have been created yet.
        cache = defaults.get_mapping("cache")
        cache.validate_keys(["quota", "storage-service", "pull-buildtrees", "cache-buildtrees"])

        cas_volume = self.casdir
        while not os.path.exists(cas_volume):
            cas_volume = os.path.dirname(cas_volume)

        self.config_cache_quota_string = cache.get_str("quota")
        try:
            self.config_cache_quota = utils._parse_size(self.config_cache_quota_string, cas_volume)
        except utils.UtilError as e:
            raise LoadError(
                "{}\nPlease specify the value in bytes or as a % of full disk space.\n"
                "\nValid values are, for example: 800M 10G 1T 50%\n".format(str(e)),
                LoadErrorReason.INVALID_DATA,
            ) from e

        remote_cache = cache.get_mapping("storage-service", default=None)
        if remote_cache:
            self.remote_cache_spec = RemoteSpec.new_from_node(remote_cache)

        # Load global artifact cache configuration
        cache_config = defaults.get_mapping("artifacts", default={})
        self._global_artifact_cache_config = _CacheConfig.new_from_node(cache_config)

        # Load global source cache configuration
        cache_config = defaults.get_mapping("source-caches", default={})
        self._global_source_cache_config = _CacheConfig.new_from_node(cache_config)

        # Load the global remote execution config
        remote_execution = defaults.get_mapping("remote-execution", default=None)
        if remote_execution:
            self.remote_execution_specs = self._load_remote_execution(remote_execution)

        # Load pull build trees configuration
        self.pull_buildtrees = cache.get_bool("pull-buildtrees")

        # Load cache build trees configuration
        self.cache_buildtrees = cache.get_enum("cache-buildtrees", _CacheBuildTrees)

        # Load logging config
        logging = defaults.get_mapping("logging")
        logging.validate_keys(
            [
                "key-length",
                "verbose",
                "error-lines",
                "message-lines",
                "debug",
                "element-format",
                "message-format",
                "throttle-ui-updates",
            ]
        )
        self.log_key_length = logging.get_int("key-length")
        self.log_debug = logging.get_bool("debug")
        self.log_verbose = logging.get_bool("verbose")
        self.log_error_lines = logging.get_int("error-lines")
        self.log_message_lines = logging.get_int("message-lines")
        self.log_element_format = logging.get_str("element-format")
        self.log_message_format = logging.get_str("message-format")
        self.log_throttle_updates = logging.get_bool("throttle-ui-updates")

        # Load scheduler config
        scheduler = defaults.get_mapping("scheduler")
        scheduler.validate_keys(["on-error", "fetchers", "builders", "pushers", "network-retries"])
        self.sched_error_action = scheduler.get_enum("on-error", _SchedulerErrorAction)
        self.sched_fetchers = scheduler.get_int("fetchers")
        self.sched_builders = scheduler.get_int("builders")
        self.sched_pushers = scheduler.get_int("pushers")
        self.sched_network_retries = scheduler.get_int("network-retries")

        # Load build config
        build = defaults.get_mapping("build")
        build.validate_keys(["max-jobs", "dependencies"])
        self.build_max_jobs = build.get_int("max-jobs")

        dependencies = build.get_str("dependencies")
        if dependencies not in ["none", "all"]:
            provenance = build.get_scalar("dependencies").get_provenance()
            raise LoadError(
                "{}: Invalid value for 'dependencies'. Choose 'none' or 'all'.".format(provenance),
                LoadErrorReason.INVALID_DATA,
            )
        self.build_dependencies = _PipelineSelection(dependencies)

        # Load fetch config
        fetch = defaults.get_mapping("fetch")
        fetch.validate_keys(["source"])
        self.fetch_source = fetch.get_enum("source", _SourceUriPolicy)

        # Load track config
        track = defaults.get_mapping("track")
        track.validate_keys(["source"])
        self.track_source = track.get_enum("source", _SourceUriPolicy)

        # Load per-projects overrides
        self._project_overrides = defaults.get_mapping("projects", default={})

        # Shallow validation of overrides, parts of buildstream which rely
        # on the overrides are expected to validate elsewhere.
        for overrides_project in self._project_overrides.keys():
            overrides = self._project_overrides.get_mapping(overrides_project)
            overrides.validate_keys(
                ["artifacts", "source-caches", "options", "strict", "default-mirror", "remote-execution", "mirrors"]
            )

    @property
    def platform(self) -> Platform:
        if not self._platform:
            self._platform = Platform.create_instance()

        return self._platform

    @property
    def artifactcache(self) -> ArtifactCache:
        if not self._artifactcache:
            self._artifactcache = ArtifactCache(self)

        return self._artifactcache

    @property
    def elementsourcescache(self) -> ElementSourcesCache:
        if not self._elementsourcescache:
            self._elementsourcescache = ElementSourcesCache(self)

        return self._elementsourcescache

    @property
    def sourcecache(self) -> SourceCache:
        if not self._sourcecache:
            self._sourcecache = SourceCache(self)

        return self._sourcecache

    # add_project():
    #
    # Add a project to the context.
    #
    # Args:
    #    project: The project to add
    #
    def add_project(self, project: "Project") -> None:
        if not self._projects:
            self._workspaces = Workspaces(project, self._workspace_project_cache)
        self._projects.append(project)

    # get_projects():
    #
    # Return the list of projects in the context.
    #
    # Returns:
    #    The list of projects
    #
    def get_projects(self) -> Iterable["Project"]:
        return self._projects

    # get_toplevel_project():
    #
    # Return the toplevel project, the one which BuildStream was
    # invoked with as opposed to a junctioned subproject.
    #
    # Returns:
    #    (Project): The toplevel Project object, or None
    #
    def get_toplevel_project(self) -> "Project":
        #
        # It is an error to call this before a toplevel
        # project is added
        #
        return self._projects[0]

    # initialize_remotes()
    #
    # This will resolve what remotes each loaded project will interact
    # with an initialize the underlying asset cache modules.
    #
    # Note that this can be called more than once, in the case that
    # Stream() has loaded additional projects during the load cycle
    # and some state needs to be recalculated.
    #
    # Args:
    #    connect_artifact_cache: Whether to try to contact remote artifact caches
    #    connect_source_cache: Whether to try to contact remote source caches
    #    artifact_remotes: Artifact cache remotes specified on the commmand line
    #    source_remotes: Source cache remotes specified on the commmand line
    #    ignore_project_artifact_remotes: Whether to ignore artifact remotes specified by projects
    #    ignore_project_source_remotes: Whether to ignore artifact remotes specified by projects
    #
    def initialize_remotes(
        self,
        connect_artifact_cache: bool,
        connect_source_cache: bool,
        artifact_remotes: Iterable[RemoteSpec] = (),
        source_remotes: Iterable[RemoteSpec] = (),
        ignore_project_artifact_remotes: bool = False,
        ignore_project_source_remotes: bool = False,
    ) -> None:

        # Ensure all projects are fully loaded.
        for project in self._projects:
            project.ensure_fully_loaded()

        #
        # If the global remote execution specs have been overridden by the
        # toplevel project, then adjust them now that we're all loaded.
        #
        project = self.get_toplevel_project()
        if project:
            override_node = self.get_overrides(project.name)
            remote_execution = override_node.get_mapping("remote-execution", default=None)
            if remote_execution:
                self.remote_execution_specs = self._load_remote_execution(remote_execution)

        #
        # Maintain our list of remote specs for artifact and source caches
        #
        for project in self._projects:
            artifact_specs: List[RemoteSpec] = []
            source_specs: List[RemoteSpec] = []

            if connect_artifact_cache:
                artifact_specs = self._resolve_specs_for_project(
                    project,
                    artifact_remotes,
                    ignore_project_artifact_remotes,
                    self._global_artifact_cache_config,
                    "artifacts",
                    "artifact_cache_specs",
                )
            if connect_source_cache:
                source_specs = self._resolve_specs_for_project(
                    project,
                    source_remotes,
                    ignore_project_source_remotes,
                    self._global_source_cache_config,
                    "source-caches",
                    "source_cache_specs",
                )

            # Advertize the per project remote specs publicly for the frontend
            self.project_artifact_cache_specs[project.name] = artifact_specs
            self.project_source_cache_specs[project.name] = source_specs

            #
            # Now that we know which remote specs are going to be used, maintain
            # our total set of overall active remote specs, this helps the asset cache
            # modules to maintain a remote connection for the required remotes.
            #
            for spec in artifact_specs:
                self._active_artifact_cache_specs.add(spec)
            for spec in source_specs:
                self._active_source_cache_specs.add(spec)

        # Now initialize the underlying asset caches
        #
        with self.messenger.timed_activity("Initializing remote caches", silent_nested=True):
            self.artifactcache.setup_remotes(self._active_artifact_cache_specs, self.project_artifact_cache_specs)
            self.elementsourcescache.setup_remotes(self._active_source_cache_specs, self.project_source_cache_specs)
            self.sourcecache.setup_remotes(self._active_source_cache_specs, self.project_source_cache_specs)

    # get_workspaces():
    #
    # Return a Workspaces object containing a list of workspaces.
    #
    # Returns:
    #    The Workspaces object
    #
    def get_workspaces(self) -> Workspaces:
        #
        # It is an error to call this early on before the Workspaces
        # has been instantiated
        #
        assert self._workspaces
        return self._workspaces

    # get_workspace_project_cache():
    #
    # Return the WorkspaceProjectCache object used for this BuildStream invocation
    #
    # Returns:
    #    The WorkspaceProjectCache object
    #
    def get_workspace_project_cache(self) -> WorkspaceProjectCache:
        return self._workspace_project_cache

    # get_overrides():
    #
    # Fetch the override dictionary for the active project. This returns
    # a node loaded from YAML.
    #
    # Args:
    #    project_name: The project name
    #
    # Returns:
    #    The overrides dictionary for the specified project
    #
    def get_overrides(self, project_name: str) -> MappingNode:
        return self._project_overrides.get_mapping(project_name, default={})

    # get_strict():
    #
    # Fetch whether we are strict or not
    #
    # Returns:
    #    Whether or not to use strict build plan
    #
    def get_strict(self) -> bool:
        if self._strict_build_plan is None:
            # Either we're not overridden or we've never worked it out before
            # so work out if we should be strict, and then cache the result
            toplevel = self.get_toplevel_project()
            overrides = self.get_overrides(toplevel.name)
            self._strict_build_plan = overrides.get_bool("strict", default=True)

        # If it was set by the CLI, it overrides any config
        # Ditto if we've already computed this, then we return the computed
        # value which we cache here too.
        return self._strict_build_plan

    def get_cascache(self) -> CASCache:
        if self._cascache is None:
            if self.log_debug:
                log_level = CASLogLevel.TRACE
            elif self.log_verbose:
                log_level = CASLogLevel.INFO
            else:
                log_level = CASLogLevel.WARNING

            self._cascache = CASCache(
                self.cachedir,
                casd=self.use_casd,
                cache_quota=self.config_cache_quota,
                remote_cache_spec=self.remote_cache_spec,
                log_level=log_level,
                log_directory=self.logdir,
                messenger=self.messenger,
            )
        return self._cascache

    ######################################################
    #                  Private methods                   #
    ######################################################

    # _resolve_specs_for_project()
    #
    # Helper function to resolve which remote specs apply for a given project
    #
    # Args:
    #    project: The project
    #    cli_remotes: The remotes specified in the CLI
    #    cli_override: Whether the CLI decided to override project suggestions
    #    global_config: The global user configuration for this remote type
    #    override_key: The key to lookup project overrides for this remote type
    #    project_attribute: The Project attribute for project suggestions
    #
    # Returns:
    #    The resolved remotes for this project.
    #
    def _resolve_specs_for_project(
        self,
        project: "Project",
        cli_remotes: Iterable[RemoteSpec],
        cli_override: bool,
        global_config: _CacheConfig,
        override_key: str,
        project_attribute: str,
    ) -> List[RemoteSpec]:

        # Early return if the CLI is taking full control
        if cli_override and cli_remotes:
            return list(cli_remotes)

        # Obtain the overrides
        override_node = self.get_overrides(project.name)
        override_config_node = override_node.get_mapping(override_key, default={})
        override_config = _CacheConfig.new_from_node(override_config_node)

        #
        # Decide on what remotes to use from user config, if any
        #
        # Priority CLI -> Project overrides -> Global config
        #
        remotes: List[RemoteSpec]
        if cli_remotes:
            remotes = list(cli_remotes)
        elif override_config.remote_specs:
            remotes = override_config.remote_specs
        else:
            remotes = global_config.remote_specs

        # If any of the configs have disabled project remotes, return now
        #
        if cli_override or override_config.override_projects or global_config.override_projects:
            return remotes

        # If there are any project recommendations, append them at the end
        project_remotes = getattr(project, project_attribute)
        remotes = list(utils._deduplicate(remotes + project_remotes))

        return remotes

    # Force the resolved XDG variables into the environment,
    # this is so that they can be used directly to specify
    # preferred locations of things from user configuration
    # files.
    def _init_xdg(self) -> None:
        if not os.environ.get("XDG_CACHE_HOME"):
            os.environ["XDG_CACHE_HOME"] = os.path.expanduser("~/.cache")
        if not os.environ.get("XDG_CONFIG_HOME"):
            os.environ["XDG_CONFIG_HOME"] = os.path.expanduser("~/.config")
        if not os.environ.get("XDG_DATA_HOME"):
            os.environ["XDG_DATA_HOME"] = os.path.expanduser("~/.local/share")

    def _load_remote_execution(self, node: MappingNode) -> Optional[RemoteExecutionSpec]:
        return RemoteExecutionSpec.new_from_node(node, remote_cache=bool(self.remote_cache_spec))
