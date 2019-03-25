#  Copyright (C) 2019 Bloomberg Finance LP
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
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#
from collections.abc import Mapping
import multiprocessing

from . import utils
from . import _yaml
from ._cas import CASRemote
from ._message import Message, MessageType


# Base Cache for Caches to derive from
#
class BaseCache():

    # None of these should ever be called in the base class, but this appeases
    # pylint to some degree
    spec_class = None
    spec_name = None
    spec_error = None
    config_node_name = None

    def __init__(self, context):
        self.context = context
        self.cas = context.get_cascache()
        self.casquota = context.get_casquota()
        self.casquota._calculate_cache_quota()

        self._remotes_setup = False           # Check to prevent double-setup of remotes
        # Per-project list of _CASRemote instances.
        self._remotes = {}

        self.global_remote_specs = []
        self.project_remote_specs = {}

        self._has_fetch_remotes = False
        self._has_push_remotes = False

    # specs_from_config_node()
    #
    # Parses the configuration of remote artifact caches from a config block.
    #
    # Args:
    #   config_node (dict): The config block, which may contain the 'artifacts' key
    #   basedir (str): The base directory for relative paths
    #
    # Returns:
    #   A list of ArtifactCacheSpec instances.
    #
    # Raises:
    #   LoadError, if the config block contains invalid keys.
    #
    @classmethod
    def specs_from_config_node(cls, config_node, basedir=None):
        cache_specs = []

        artifacts = config_node.get(cls.config_node_name, [])
        if isinstance(artifacts, Mapping):
            # pylint: disable=not-callable
            cache_specs.append(cls.spec_class._new_from_config_node(artifacts, basedir))
        elif isinstance(artifacts, list):
            for spec_node in artifacts:
                cache_specs.append(cls.spec_class._new_from_config_node(spec_node, basedir))
        else:
            provenance = _yaml.node_get_provenance(config_node, key=cls.config_node_name)
            raise _yaml.LoadError(_yaml.LoadErrorReason.INVALID_DATA,
                                  "%s: 'artifacts' must be a single 'url:' mapping, or a list of mappings" %
                                  (str(provenance)))
        return cache_specs

    # _configured_remote_cache_specs():
    #
    # Return the list of configured remotes for a given project, in priority
    # order. This takes into account the user and project configuration.
    #
    # Args:
    #     context (Context): The BuildStream context
    #     project (Project): The BuildStream project
    #
    # Returns:
    #   A list of ArtifactCacheSpec instances describing the remote artifact caches.
    #
    @classmethod
    def _configured_remote_cache_specs(cls, context, project):
        project_overrides = context.get_overrides(project.name)
        project_extra_specs = cls.specs_from_config_node(project_overrides)

        project_specs = getattr(project, cls.spec_name)
        context_specs = getattr(context, cls.spec_name)

        return list(utils._deduplicate(
            project_extra_specs + project_specs + context_specs))

    # setup_remotes():
    #
    # Sets up which remotes to use
    #
    # Args:
    #    use_config (bool): Whether to use project configuration
    #    remote_url (str): Remote cache URL
    #
    # This requires that all of the projects which are to be processed in the session
    # have already been loaded and are observable in the Context.
    #
    def setup_remotes(self, *, use_config=False, remote_url=None):

        # Ensure we do not double-initialise since this can be expensive
        assert not self._remotes_setup
        self._remotes_setup = True

        # Initialize remote caches. We allow the commandline to override
        # the user config in some cases (for example `bst artifact push --remote=...`).
        has_remote_caches = False
        if remote_url:
            # pylint: disable=not-callable
            self._set_remotes([self.spec_class(remote_url, push=True)])
            has_remote_caches = True
        if use_config:
            for project in self.context.get_projects():
                caches = self._configured_remote_cache_specs(self.context, project)
                if caches:  # caches is a list of spec_class instances
                    self._set_remotes(caches, project=project)
                    has_remote_caches = True
        if has_remote_caches:
            self._initialize_remotes()

    # initialize_remotes():
    #
    # This will contact each remote cache.
    #
    # Args:
    #     on_failure (callable): Called if we fail to contact one of the caches.
    #
    def initialize_remotes(self, *, on_failure=None):
        remote_specs = self.global_remote_specs

        for project in self.project_remote_specs:
            remote_specs += self.project_remote_specs[project]

        remote_specs = list(utils._deduplicate(remote_specs))

        remotes = {}
        q = multiprocessing.Queue()
        for remote_spec in remote_specs:

            error = CASRemote.check_remote(remote_spec, q)

            if error and on_failure:
                on_failure(remote_spec.url, error)
            elif error:
                raise self.spec_error(error)  # pylint: disable=not-callable
            else:
                self._has_fetch_remotes = True
                if remote_spec.push:
                    self._has_push_remotes = True

                remotes[remote_spec.url] = CASRemote(remote_spec)

        for project in self.context.get_projects():
            remote_specs = self.global_remote_specs
            if project in self.project_remote_specs:
                remote_specs = list(utils._deduplicate(remote_specs + self.project_remote_specs[project]))

            project_remotes = []

            for remote_spec in remote_specs:
                # Errors are already handled in the loop above,
                # skip unreachable remotes here.
                if remote_spec.url not in remotes:
                    continue

                remote = remotes[remote_spec.url]
                project_remotes.append(remote)

            self._remotes[project] = project_remotes

    # has_fetch_remotes():
    #
    # Check whether any remote repositories are available for fetching.
    #
    # Args:
    #     plugin (Plugin): The Plugin to check
    #
    # Returns: True if any remote repositories are configured, False otherwise
    #
    def has_fetch_remotes(self, *, plugin=None):
        if not self._has_fetch_remotes:
            # No project has fetch remotes
            return False
        elif plugin is None:
            # At least one (sub)project has fetch remotes
            return True
        else:
            # Check whether the specified element's project has fetch remotes
            remotes_for_project = self._remotes[plugin._get_project()]
            return bool(remotes_for_project)

    # has_push_remotes():
    #
    # Check whether any remote repositories are available for pushing.
    #
    # Args:
    #     element (Element): The Element to check
    #
    # Returns: True if any remote repository is configured, False otherwise
    #
    def has_push_remotes(self, *, plugin=None):
        if not self._has_push_remotes:
            # No project has push remotes
            return False
        elif plugin is None:
            # At least one (sub)project has push remotes
            return True
        else:
            # Check whether the specified element's project has push remotes
            remotes_for_project = self._remotes[plugin._get_project()]
            return any(remote.spec.push for remote in remotes_for_project)

    ################################################
    #               Local Private Methods          #
    ################################################

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context.message(
            Message(None, message_type, message, **args))

    # _set_remotes():
    #
    # Set the list of remote caches. If project is None, the global list of
    # remote caches will be set, which is used by all projects. If a project is
    # specified, the per-project list of remote caches will be set.
    #
    # Args:
    #     remote_specs (list): List of ArtifactCacheSpec instances, in priority order.
    #     project (Project): The Project instance for project-specific remotes
    def _set_remotes(self, remote_specs, *, project=None):
        if project is None:
            # global remotes
            self.global_remote_specs = remote_specs
        else:
            self.project_remote_specs[project] = remote_specs

    # _initialize_remotes()
    #
    # An internal wrapper which calls the abstract method and
    # reports takes care of messaging
    #
    def _initialize_remotes(self):
        def remote_failed(url, error):
            self._message(MessageType.WARN, "Failed to initialize remote {}: {}".format(url, error))

        with self.context.timed_activity("Initializing remote caches", silent_nested=True):
            self.initialize_remotes(on_failure=remote_failed)
