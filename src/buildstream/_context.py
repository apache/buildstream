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
from . import _cachekey
from . import _site
from . import _yaml
from ._exceptions import LoadError, LoadErrorReason
from ._messenger import Messenger
from ._profile import Topics, PROFILER
from ._artifactcache import ArtifactCache
from ._sourcecache import SourceCache
from ._cas import CASCache, CASQuota, CASCacheUsage
from ._workspaces import Workspaces, WorkspaceProjectCache
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
class Context():

    def __init__(self):

        # Filename indicating which configuration file was used, or None for the defaults
        self.config_origin = None

        # The directory under which other directories are based
        self.cachedir = None

        # The directory where various sources are stored
        self.sourcedir = None

        # specs for source cache remotes
        self.source_cache_specs = None

        # The directory where build sandboxes will be created
        self.builddir = None

        # The directory for CAS
        self.casdir = None

        # The directory for artifact protos
        self.artifactdir = None

        # The directory for temporary files
        self.tmpdir = None

        # Default root location for workspaces
        self.workspacedir = None

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
        self._cache_key = None
        self._artifactcache = None
        self._sourcecache = None
        self._projects = []
        self._project_overrides = _yaml.new_empty_node()
        self._workspaces = None
        self._workspace_project_cache = WorkspaceProjectCache()
        self._cascache = None
        self._casquota = None

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
            default_config = os.path.join(os.environ['XDG_CONFIG_HOME'],
                                          'buildstream.conf')
            if os.path.exists(default_config):
                config = default_config

        # Load default config
        #
        defaults = _yaml.load(_site.default_user_config)

        if config:
            self.config_origin = os.path.abspath(config)
            user_config = _yaml.load(config)
            _yaml.composite(defaults, user_config)

        # Give obsoletion warnings
        if 'builddir' in defaults:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "builddir is obsolete, use cachedir")

        if 'artifactdir' in defaults:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "artifactdir is obsolete")

        _yaml.node_validate(defaults, [
            'cachedir', 'sourcedir', 'builddir', 'logdir', 'scheduler',
            'artifacts', 'source-caches', 'logging', 'projects', 'cache', 'prompt',
            'workspacedir', 'remote-execution',
        ])

        for directory in ['cachedir', 'sourcedir', 'logdir', 'workspacedir']:
            # Allow the ~ tilde expansion and any environment variables in
            # path specification in the config files.
            #
            path = defaults.get_str(directory)
            path = os.path.expanduser(path)
            path = os.path.expandvars(path)
            path = os.path.normpath(path)
            setattr(self, directory, path)

        # add directories not set by users
        self.tmpdir = os.path.join(self.cachedir, 'tmp')
        self.casdir = os.path.join(self.cachedir, 'cas')
        self.builddir = os.path.join(self.cachedir, 'build')
        self.artifactdir = os.path.join(self.cachedir, 'artifacts', 'refs')

        # Move old artifact cas to cas if it exists and create symlink
        old_casdir = os.path.join(self.cachedir, 'artifacts', 'cas')
        if (os.path.exists(old_casdir) and not os.path.islink(old_casdir) and
                not os.path.exists(self.casdir)):
            os.rename(old_casdir, self.casdir)
            os.symlink(self.casdir, old_casdir)

        # Cleanup old extract directories
        old_extractdirs = [os.path.join(self.cachedir, 'artifacts', 'extract'),
                           os.path.join(self.cachedir, 'extract')]
        for old_extractdir in old_extractdirs:
            if os.path.isdir(old_extractdir):
                shutil.rmtree(old_extractdir, ignore_errors=True)

        # Load quota configuration
        # We need to find the first existing directory in the path of our
        # cachedir - the cachedir may not have been created yet.
        cache = defaults.get_mapping('cache')
        _yaml.node_validate(cache, ['quota', 'pull-buildtrees', 'cache-buildtrees'])

        self.config_cache_quota_string = cache.get_str('quota')
        try:
            self.config_cache_quota = utils._parse_size(self.config_cache_quota_string,
                                                        self.casdir)
        except utils.UtilError as e:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}\nPlease specify the value in bytes or as a % of full disk space.\n"
                            "\nValid values are, for example: 800M 10G 1T 50%\n"
                            .format(str(e))) from e

        # Load artifact share configuration
        self.artifact_cache_specs = ArtifactCache.specs_from_config_node(defaults)

        # Load source cache config
        self.source_cache_specs = SourceCache.specs_from_config_node(defaults)

        # Load remote execution config getting pull-artifact-files from it
        remote_execution = defaults.get_mapping('remote-execution', default=None)
        if remote_execution:
            self.pull_artifact_files = _yaml.node_get(
                remote_execution, bool, 'pull-artifact-files', default_value=True)
            # This stops it being used in the remote service set up
            _yaml.node_del(remote_execution, 'pull-artifact-files', safe=True)
            # Don't pass the remote execution settings if that was the only option
            if _yaml.node_keys(remote_execution) == []:
                _yaml.node_del(defaults, 'remote-execution')
        else:
            self.pull_artifact_files = True

        self.remote_execution_specs = SandboxRemote.specs_from_config_node(defaults)

        # Load pull build trees configuration
        self.pull_buildtrees = _yaml.node_get(cache, bool, 'pull-buildtrees')

        # Load cache build trees configuration
        self.cache_buildtrees = _node_get_option_str(
            cache, 'cache-buildtrees', ['always', 'auto', 'never'])

        # Load logging config
        logging = defaults.get_mapping('logging')
        _yaml.node_validate(logging, [
            'key-length', 'verbose',
            'error-lines', 'message-lines',
            'debug', 'element-format', 'message-format'
        ])
        self.log_key_length = _yaml.node_get(logging, int, 'key-length')
        self.log_debug = _yaml.node_get(logging, bool, 'debug')
        self.log_verbose = _yaml.node_get(logging, bool, 'verbose')
        self.log_error_lines = _yaml.node_get(logging, int, 'error-lines')
        self.log_message_lines = _yaml.node_get(logging, int, 'message-lines')
        self.log_element_format = logging.get_str('element-format')
        self.log_message_format = logging.get_str('message-format')

        # Load scheduler config
        scheduler = defaults.get_mapping('scheduler')
        _yaml.node_validate(scheduler, [
            'on-error', 'fetchers', 'builders',
            'pushers', 'network-retries'
        ])
        self.sched_error_action = _node_get_option_str(
            scheduler, 'on-error', ['continue', 'quit', 'terminate'])
        self.sched_fetchers = _yaml.node_get(scheduler, int, 'fetchers')
        self.sched_builders = _yaml.node_get(scheduler, int, 'builders')
        self.sched_pushers = _yaml.node_get(scheduler, int, 'pushers')
        self.sched_network_retries = _yaml.node_get(scheduler, int, 'network-retries')

        # Load per-projects overrides
        self._project_overrides = defaults.get_mapping('projects', default={})

        # Shallow validation of overrides, parts of buildstream which rely
        # on the overrides are expected to validate elsewhere.
        for _, overrides in _yaml.node_items(self._project_overrides):
            _yaml.node_validate(overrides,
                                ['artifacts', 'source-caches', 'options',
                                 'strict', 'default-mirror',
                                 'remote-execution'])

    @property
    def artifactcache(self):
        if not self._artifactcache:
            self._artifactcache = ArtifactCache(self)

        return self._artifactcache

    # get_cache_usage()
    #
    # Fetches the current usage of the artifact cache
    #
    # Returns:
    #     (CASCacheUsage): The current status
    #
    def get_cache_usage(self):
        return CASCacheUsage(self.get_casquota())

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
    # a node loaded from YAML and as such, values loaded from the returned
    # node should be loaded using the _yaml.node_get() family of functions.
    #
    # Args:
    #    project_name (str): The project name
    #
    # Returns:
    #    (dict): The overrides dictionary for the specified project
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
            self._strict_build_plan = _yaml.node_get(overrides, bool, 'strict', default_value=True)

        # If it was set by the CLI, it overrides any config
        # Ditto if we've already computed this, then we return the computed
        # value which we cache here too.
        return self._strict_build_plan

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
            self._cache_key = _cachekey.generate_key(_yaml.new_empty_node())

        return self._cache_key

    # set_artifact_directories_optional()
    #
    # This indicates that the current context (command or configuration)
    # does not require directory trees of all artifacts to be available in the
    # local cache.
    #
    def set_artifact_directories_optional(self):
        self.require_artifact_directories = False
        self.require_artifact_files = False

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
        if not os.environ.get('XDG_CACHE_HOME'):
            os.environ['XDG_CACHE_HOME'] = os.path.expanduser('~/.cache')
        if not os.environ.get('XDG_CONFIG_HOME'):
            os.environ['XDG_CONFIG_HOME'] = os.path.expanduser('~/.config')
        if not os.environ.get('XDG_DATA_HOME'):
            os.environ['XDG_DATA_HOME'] = os.path.expanduser('~/.local/share')

    def get_cascache(self):
        if self._cascache is None:
            self._cascache = CASCache(self.cachedir)
        return self._cascache

    def get_casquota(self):
        if self._casquota is None:
            self._casquota = CASQuota(self)
        return self._casquota


# _node_get_option_str()
#
# Like _yaml.node_get(), but also checks value is one of the allowed option
# strings. Fetches a value from a dictionary node, and makes sure it's one of
# the pre-defined options.
#
# Args:
#    node (dict): The dictionary node
#    key (str): The key to get a value for in node
#    allowed_options (iterable): Only accept these values
#
# Returns:
#    The value, if found in 'node'.
#
# Raises:
#    LoadError, when the value is not of the expected type, or is not found.
#
def _node_get_option_str(node, key, allowed_options):
    result = node.get_str(key)
    if result not in allowed_options:
        provenance = _yaml.node_get_provenance(node, key)
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "{}: {} should be one of: {}".format(
                            provenance, key, ", ".join(allowed_options)))
    return result
