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
from ._sourcecache import SourceCache
from ._cas import CASCache, CASLogLevel
from .types import _CacheBuildTrees, _PipelineSelection, _SchedulerErrorAction
from ._workspaces import Workspaces, WorkspaceProjectCache
from .node import Node
from .sandbox import SandboxRemote


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
    def __init__(self, *, use_casd=True):

        # Whether we are running as part of a test suite. This is only relevant
        # for developing BuildStream itself.
        self.is_running_in_test_suite = "BST_TEST_SUITE" in os.environ

        # Filename indicating which configuration file was used, or None for the defaults
        self.config_origin = None

        # The directory under which other directories are based
        self.cachedir = None

        # The directory where various sources are stored
        self.sourcedir = None

        # The directory where build sandboxes will be created
        self.builddir = None

        # The directory for CAS
        self.casdir = None

        # Whether to use casd - meant for interfaces such as
        # completion where casd is not required
        self.use_casd = use_casd

        # The directory for artifact protos
        self.artifactdir = None

        # The directory for temporary files
        self.tmpdir = None

        # Default root location for workspaces
        self.workspacedir = None

        # specs for source cache remotes
        self.source_cache_specs = None

        # The locations from which to push and pull prebuilt artifacts
        self.artifact_cache_specs = None

        # The global remote execution configuration
        self.remote_execution_specs = None

        # The directory to store build logs
        self.logdir = None

        # The abbreviated cache key length to display in the UI
        self.log_key_length = None

        # Whether debug mode is enabled
        self.log_debug = None

        # Whether verbose mode is enabled
        self.log_verbose = None

        # Maximum number of lines to print from build logs
        self.log_error_lines = None

        # Maximum number of lines to print in the master log for a detailed message
        self.log_message_lines = None

        # Format string for printing the pipeline at startup time
        self.log_element_format = None

        # Format string for printing message lines in the master log
        self.log_message_format = None

        # Wether to rate limit the updating of the bst output where applicable
        self.log_throttle_updates = None

        # Maximum number of fetch or refresh tasks
        self.sched_fetchers = None

        # Maximum number of build tasks
        self.sched_builders = None

        # Maximum number of push tasks
        self.sched_pushers = None

        # Maximum number of retries for network tasks
        self.sched_network_retries = None

        # What to do when a build fails in non interactive mode
        self.sched_error_action = None

        # Maximum jobs per build
        self.build_max_jobs = None

        # Control which dependencies to build
        self.build_dependencies = None

        # Size of the artifact cache in bytes
        self.config_cache_quota = None

        # User specified cache quota, used for display messages
        self.config_cache_quota_string = None

        # Whether or not to attempt to pull build trees globally
        self.pull_buildtrees = None

        # Whether to pull the files of an artifact when doing remote execution
        self.pull_artifact_files = None

        # Whether or not to cache build trees on artifact creation
        self.cache_buildtrees = None

        # Whether directory trees are required for all artifacts in the local cache
        self.require_artifact_directories = True

        # Whether file contents are required for all artifacts in the local cache
        self.require_artifact_files = True

        # Whether elements must be rebuilt when their dependencies have changed
        self._strict_build_plan = None

        # Make sure the XDG vars are set in the environment before loading anything
        self._init_xdg()

        self.messenger = Messenger()

        # Private variables
        self._platform = None
        self._artifactcache = None
        self._sourcecache = None
        self._projects = []
        self._project_overrides = Node.from_dict({})
        self._workspaces = None
        self._workspace_project_cache = WorkspaceProjectCache()
        self._cascache = None

    # __enter__()
    #
    # Called when entering the with-statement context.
    #
    def __enter__(self):
        return self

    # __exit__()
    #
    # Called when exiting the with-statement context.
    #
    def __exit__(self, exc_type, exc_value, traceback):
        if self._artifactcache:
            self._artifactcache.release_resources()

        if self._sourcecache:
            self._sourcecache.release_resources()

        if self._cascache:
            self._cascache.release_resources(self.messenger)

    # load()
    #
    # Loads the configuration files
    #
    # Args:
    #    config (filename): The user specified configuration file, if any
    #
    # Raises:
    #   LoadError
    #
    # This will first load the BuildStream default configuration and then
    # override that configuration with the configuration file indicated
    # by *config*, if any was specified.
    #
    @PROFILER.profile(Topics.LOAD_CONTEXT, "load")
    def load(self, config=None):
        # If a specific config file is not specified, default to trying
        # a $XDG_CONFIG_HOME/buildstream.conf file
        #
        if not config:
            #
            # Support parallel installations of BuildStream by first
            # trying a (major point) version specific configuration file
            # and then falling back to buildstream.conf.
            #
            major_version, _ = utils._get_bst_api_version()
            for config_filename in ("buildstream{}.conf".format(major_version), "buildstream.conf"):
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
                "artifacts",
                "source-caches",
                "logging",
                "projects",
                "cache",
                "prompt",
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
        old_extractdirs = [os.path.join(self.cachedir, "artifacts", "extract"), os.path.join(self.cachedir, "extract")]
        for old_extractdir in old_extractdirs:
            if os.path.isdir(old_extractdir):
                shutil.rmtree(old_extractdir, ignore_errors=True)

        # Load quota configuration
        # We need to find the first existing directory in the path of our
        # casdir - the casdir may not have been created yet.
        cache = defaults.get_mapping("cache")
        cache.validate_keys(["quota", "pull-buildtrees", "cache-buildtrees"])

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

        # Load artifact share configuration
        self.artifact_cache_specs = ArtifactCache.specs_from_config_node(defaults)

        # Load source cache config
        self.source_cache_specs = SourceCache.specs_from_config_node(defaults)

        # Load remote execution config getting pull-artifact-files from it
        remote_execution = defaults.get_mapping("remote-execution", default=None)
        if remote_execution:
            self.pull_artifact_files = remote_execution.get_bool("pull-artifact-files", default=True)
            # This stops it being used in the remote service set up
            remote_execution.safe_del("pull-artifact-files")
            # Don't pass the remote execution settings if that was the only option
            if remote_execution.keys() == []:
                del defaults["remote-execution"]
        else:
            self.pull_artifact_files = True

        self.remote_execution_specs = SandboxRemote.specs_from_config_node(defaults)

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
        if dependencies not in ["plan", "all"]:
            provenance = build.get_scalar("dependencies").get_provenance()
            raise LoadError(
                "{}: Invalid value for 'dependencies'. Choose 'plan' or 'all'.".format(provenance),
                LoadErrorReason.INVALID_DATA,
            )
        self.build_dependencies = _PipelineSelection(dependencies)

        # Load per-projects overrides
        self._project_overrides = defaults.get_mapping("projects", default={})

        # Shallow validation of overrides, parts of buildstream which rely
        # on the overrides are expected to validate elsewhere.
        for overrides_project in self._project_overrides.keys():
            overrides = self._project_overrides.get_mapping(overrides_project)
            overrides.validate_keys(
                ["artifacts", "source-caches", "options", "strict", "default-mirror", "remote-execution"]
            )

    @property
    def platform(self):
        if not self._platform:
            self._platform = Platform.create_instance()

        return self._platform

    @property
    def artifactcache(self):
        if not self._artifactcache:
            self._artifactcache = ArtifactCache(self)

        return self._artifactcache

    @property
    def sourcecache(self):
        if not self._sourcecache:
            self._sourcecache = SourceCache(self)

        return self._sourcecache

    # add_project():
    #
    # Add a project to the context.
    #
    # Args:
    #    project (Project): The project to add
    #
    def add_project(self, project):
        if not self._projects:
            self._workspaces = Workspaces(project, self._workspace_project_cache)
        self._projects.append(project)

    # get_projects():
    #
    # Return the list of projects in the context.
    #
    # Returns:
    #    (list): The list of projects
    #
    def get_projects(self):
        return self._projects

    # get_toplevel_project():
    #
    # Return the toplevel project, the one which BuildStream was
    # invoked with as opposed to a junctioned subproject.
    #
    # Returns:
    #    (Project): The Project object
    #
    def get_toplevel_project(self):
        return self._projects[0]

    # get_workspaces():
    #
    # Return a Workspaces object containing a list of workspaces.
    #
    # Returns:
    #    (Workspaces): The Workspaces object
    #
    def get_workspaces(self):
        return self._workspaces

    # get_workspace_project_cache():
    #
    # Return the WorkspaceProjectCache object used for this BuildStream invocation
    #
    # Returns:
    #    (WorkspaceProjectCache): The WorkspaceProjectCache object
    #
    def get_workspace_project_cache(self):
        return self._workspace_project_cache

    # get_overrides():
    #
    # Fetch the override dictionary for the active project. This returns
    # a node loaded from YAML.
    #
    # Args:
    #    project_name (str): The project name
    #
    # Returns:
    #    (MappingNode): The overrides dictionary for the specified project
    #
    def get_overrides(self, project_name):
        return self._project_overrides.get_mapping(project_name, default={})

    # get_strict():
    #
    # Fetch whether we are strict or not
    #
    # Returns:
    #    (bool): Whether or not to use strict build plan
    #
    def get_strict(self):
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

    # set_artifact_files_optional()
    #
    # This indicates that the current context (command or configuration)
    # does not require file contents of all artifacts to be available in the
    # local cache.
    #
    def set_artifact_files_optional(self):
        self.require_artifact_files = False

    # Force the resolved XDG variables into the environment,
    # this is so that they can be used directly to specify
    # preferred locations of things from user configuration
    # files.
    def _init_xdg(self):
        if not os.environ.get("XDG_CACHE_HOME"):
            os.environ["XDG_CACHE_HOME"] = os.path.expanduser("~/.cache")
        if not os.environ.get("XDG_CONFIG_HOME"):
            os.environ["XDG_CONFIG_HOME"] = os.path.expanduser("~/.config")
        if not os.environ.get("XDG_DATA_HOME"):
            os.environ["XDG_DATA_HOME"] = os.path.expanduser("~/.local/share")

    def get_cascache(self):
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
                log_level=log_level,
                log_directory=self.logdir,
            )
        return self._cascache

    # prepare_fork():
    #
    # Prepare this process for fork without exec. This is a safeguard against
    # fork issues with multiple threads and gRPC connections.
    #
    def prepare_fork(self):
        # gRPC channels must be closed before fork.
        for cache in [self._cascache, self._artifactcache, self._sourcecache]:
            if cache:
                cache.close_grpc_channels()

        # Do not allow fork if there are background threads.
        return utils._is_single_threaded()
