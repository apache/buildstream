#  Copyright (C) 2019-2020 Bloomberg Finance LP
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
import os
from fnmatch import fnmatch
from itertools import chain
from typing import TYPE_CHECKING
import grpc

from . import utils
from . import _yaml
from ._cas import CASRemote
from ._message import Message, MessageType
from ._exceptions import AssetCacheError, LoadError, RemoteError
from ._remote import BaseRemote, RemoteSpec, RemoteType
from ._protos.build.bazel.remote.asset.v1 import remote_asset_pb2, remote_asset_pb2_grpc
from ._protos.google.rpc import code_pb2


if TYPE_CHECKING:
    from typing import Optional, Type
    from ._exceptions import BstError


class AssetRemote(BaseRemote):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fetch_service = None
        self.push_service = None

    def close(self):
        self.fetch_service = None
        self.push_service = None
        super().close()

    def _configure_protocols(self):
        # set up remote asset stubs
        self.fetch_service = remote_asset_pb2_grpc.FetchStub(self.channel)
        self.push_service = remote_asset_pb2_grpc.PushStub(self.channel)

    # _check():
    #
    # Check if this remote provides everything required for the
    # particular kind of remote. This is expected to be called as part
    # of check()
    #
    # Raises:
    #     RemoteError: If the upstream has a problem
    #
    def _check(self):
        request = remote_asset_pb2.FetchBlobRequest()
        if self.instance_name:
            request.instance_name = self.instance_name

        try:
            self.fetch_service.FetchBlob(request)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                # Expected error as the request doesn't specify any URIs.
                pass
            elif e.code() == grpc.StatusCode.UNIMPLEMENTED:
                raise RemoteError(
                    "Configured remote does not implement the Remote Asset "
                    "Fetch service. Please check remote configuration."
                )
            else:
                raise RemoteError("Remote initialisation failed with status {}: {}".format(e.code().name, e.details()))

        if self.spec.push:
            request = remote_asset_pb2.PushBlobRequest()
            if self.instance_name:
                request.instance_name = self.instance_name

            try:
                self.push_service.PushBlob(request)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                    # Expected error as the request doesn't specify any URIs.
                    pass
                elif e.code() == grpc.StatusCode.UNIMPLEMENTED:
                    raise RemoteError(
                        "Configured remote does not implement the Remote Asset "
                        "Push service. Please check remote configuration."
                    )
                else:
                    raise RemoteError(
                        "Remote initialisation failed with status {}: {}".format(e.code().name, e.details())
                    )

    # fetch_blob():
    #
    # Resolve URIs to a CAS blob digest.
    #
    # Args:
    #    uris (list of str): The URIs to resolve. Multiple URIs should represent
    #                        the same content available at different locations.
    #    qualifiers (list of Qualifier): Optional qualifiers sub-specifying the
    #                                    content to fetch.
    #
    # Returns
    #    (FetchBlobResponse): The asset server response or None if the resource
    #                         is not available.
    #
    # Raises:
    #     AssetCacheError: If the upstream has a problem
    #
    def fetch_blob(self, uris, *, qualifiers=None):
        request = remote_asset_pb2.FetchBlobRequest()
        if self.instance_name:
            request.instance_name = self.instance_name
        request.uris.extend(uris)
        if qualifiers:
            request.qualifiers.extend(qualifiers)

        try:
            response = self.fetch_service.FetchBlob(request)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None

            raise AssetCacheError("FetchBlob failed with status {}: {}".format(e.code().name, e.details())) from e

        if response.status.code == code_pb2.NOT_FOUND:
            return None

        if response.status.code != code_pb2.OK:
            raise AssetCacheError("FetchBlob failed with response status {}".format(response.status.code))

        return response

    # fetch_directory():
    #
    # Resolve URIs to a CAS Directory digest.
    #
    # Args:
    #    uris (list of str): The URIs to resolve. Multiple URIs should represent
    #                        the same content available at different locations.
    #    qualifiers (list of Qualifier): Optional qualifiers sub-specifying the
    #                                    content to fetch.
    #
    # Returns
    #    (FetchDirectoryResponse): The asset server response or None if the resource
    #                              is not available.
    #
    # Raises:
    #     AssetCacheError: If the upstream has a problem
    #
    def fetch_directory(self, uris, *, qualifiers=None):
        request = remote_asset_pb2.FetchDirectoryRequest()
        if self.instance_name:
            request.instance_name = self.instance_name
        request.uris.extend(uris)
        if qualifiers:
            request.qualifiers.extend(qualifiers)

        try:
            response = self.fetch_service.FetchDirectory(request)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None

            raise AssetCacheError("FetchDirectory failed with status {}: {}".format(e.code().name, e.details())) from e

        if response.status.code == code_pb2.NOT_FOUND:
            return None

        if response.status.code != code_pb2.OK:
            raise AssetCacheError("FetchDirectory failed with response status {}".format(response.status.code))

        return response

    # push_blob():
    #
    # Associate a CAS blob digest to URIs.
    #
    # Args:
    #    uris (list of str): The URIs to associate with the blob digest.
    #    blob_digest (Digest): The CAS blob to associate.
    #    qualifiers (list of Qualifier): Optional qualifiers sub-specifying the
    #                                    content that is being pushed.
    #    references_blobs (list of Digest): Referenced blobs that need to not expire
    #                                       before expiration of this association.
    #    references_directories (list of Digest): Referenced directories that need to not expire
    #                                             before expiration of this association.
    #
    # Raises:
    #     AssetCacheError: If the upstream has a problem
    #
    def push_blob(self, uris, blob_digest, *, qualifiers=None, references_blobs=None, references_directories=None):
        request = remote_asset_pb2.PushBlobRequest()
        if self.instance_name:
            request.instance_name = self.instance_name
        request.uris.extend(uris)
        request.blob_digest.CopyFrom(blob_digest)
        if qualifiers:
            request.qualifiers.extend(qualifiers)
        if references_blobs:
            request.references_blobs.extend(references_blobs)
        if references_directories:
            request.references_directories.extend(references_directories)

        try:
            self.push_service.PushBlob(request)
        except grpc.RpcError as e:
            raise AssetCacheError("PushBlob failed with status {}: {}".format(e.code().name, e.details())) from e

    # push_directory():
    #
    # Associate a CAS Directory digest to URIs.
    #
    # Args:
    #    uris (list of str): The URIs to associate with the blob digest.
    #    directory_digest (Digest): The CAS Direcdtory to associate.
    #    qualifiers (list of Qualifier): Optional qualifiers sub-specifying the
    #                                    content that is being pushed.
    #    references_blobs (list of Digest): Referenced blobs that need to not expire
    #                                       before expiration of this association.
    #    references_directories (list of Digest): Referenced directories that need to not expire
    #                                             before expiration of this association.
    #
    # Raises:
    #     AssetCacheError: If the upstream has a problem
    #
    def push_directory(
        self, uris, directory_digest, *, qualifiers=None, references_blobs=None, references_directories=None
    ):
        request = remote_asset_pb2.PushDirectoryRequest()
        if self.instance_name:
            request.instance_name = self.instance_name
        request.uris.extend(uris)
        request.root_directory_digest.CopyFrom(directory_digest)
        if qualifiers:
            request.qualifiers.extend(qualifiers)
        if references_blobs:
            request.references_blobs.extend(references_blobs)
        if references_directories:
            request.references_directories.extend(references_directories)

        try:
            self.push_service.PushDirectory(request)
        except grpc.RpcError as e:
            raise AssetCacheError("PushDirectory failed with status {}: {}".format(e.code().name, e.details())) from e


# Base Asset Cache for Caches to derive from
#
class AssetCache:

    # None of these should ever be called in the base class, but this appeases
    # pylint to some degree
    spec_name = None  # type: str
    config_node_name = None  # type: str

    def __init__(self, context):
        self.context = context
        self.cas = context.get_cascache()

        self._remotes_setup = False  # Check to prevent double-setup of remotes
        # Per-project list of Remote instances.
        self._storage_remotes = {}
        self._index_remotes = {}

        self.global_remote_specs = []
        self.project_remote_specs = {}

        self._has_fetch_remotes = False
        self._has_push_remotes = False

        self._basedir = None

    # close_grpc_channels():
    #
    # Close open gRPC channels.
    #
    def close_grpc_channels(self):
        # Close all remotes and their gRPC channels
        for project_remotes in chain(self._index_remotes.values(), self._storage_remotes.values()):
            for remote in project_remotes:
                remote.close()

    # release_resources():
    #
    # Release resources used by AssetCache.
    #
    def release_resources(self):
        self.close_grpc_channels()

    # specs_from_config_node()
    #
    # Parses the configuration of remote artifact caches from a config block.
    #
    # Args:
    #   config_node (dict): The config block, which may contain a key defined by cls.config_node_name
    #   basedir (str): The base directory for relative paths
    #
    # Returns:
    #   A list of RemoteSpec instances.
    #
    # Raises:
    #   LoadError, if the config block contains invalid keys.
    #
    @classmethod
    def specs_from_config_node(cls, config_node, basedir=None):
        cache_specs = []

        try:
            artifacts = [config_node.get_mapping(cls.config_node_name)]
        except LoadError:
            try:
                artifacts = config_node.get_sequence(cls.config_node_name, default=[])
            except LoadError:
                provenance = config_node.get_node(cls.config_node_name).get_provenance()
                raise _yaml.LoadError(
                    "{}: '{}' must be a single remote mapping, or a list of mappings".format(
                        provenance, cls.config_node_name
                    ),
                    _yaml.LoadErrorReason.INVALID_DATA,
                )

        for spec_node in artifacts:
            cache_specs.append(RemoteSpec.new_from_config_node(spec_node))

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
    #   A list of RemoteSpec instances describing the remote caches.
    #
    @classmethod
    def _configured_remote_cache_specs(cls, context, project):
        project_overrides = context.get_overrides(project.name)
        project_extra_specs = cls.specs_from_config_node(project_overrides)

        project_specs = getattr(project, cls.spec_name)
        context_specs = getattr(context, cls.spec_name)

        return list(utils._deduplicate(project_extra_specs + project_specs + context_specs))

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
        if self._remotes_setup:
            return

        self._remotes_setup = True

        # Initialize remote caches. We allow the commandline to override
        # the user config in some cases (for example `bst artifact push --remote=...`).
        has_remote_caches = False
        if remote_url:
            self._set_remotes([RemoteSpec(remote_url, push=True)])
            has_remote_caches = True
        if use_config:
            for project in self.context.get_projects():
                caches = self._configured_remote_cache_specs(self.context, project)
                if caches:  # caches is a list of RemoteSpec instances
                    self._set_remotes(caches, project=project)
                    has_remote_caches = True
        if has_remote_caches:
            self._initialize_remotes()

    # Notify remotes that forking is disabled
    def notify_fork_disabled(self):
        for project in self._index_remotes:
            for remote in self._index_remotes[project]:
                remote.notify_fork_disabled()
        for project in self._storage_remotes:
            for remote in self._storage_remotes[project]:
                remote.notify_fork_disabled()

    # initialize_remotes():
    #
    # This will contact each remote cache.
    #
    # Args:
    #     on_failure (callable): Called if we fail to contact one of the caches.
    #
    def initialize_remotes(self, *, on_failure=None):
        index_remotes, storage_remotes = self._create_remote_instances(on_failure=on_failure)

        # Assign remote instances to their respective projects
        for project in self.context.get_projects():
            # Get the list of specs that should be considered for this
            # project
            remote_specs = self.global_remote_specs.copy()
            if project in self.project_remote_specs:
                remote_specs.extend(self.project_remote_specs[project])

            # De-duplicate the list
            remote_specs = list(utils._deduplicate(remote_specs))

            def get_remotes(remote_list, remote_specs):
                for remote_spec in remote_specs:
                    # If a remote_spec didn't make it into the remotes
                    # dict, that means we can't access it, and it has been
                    # disabled for this session.
                    if remote_spec not in remote_list:
                        continue

                    yield remote_list[remote_spec]

            self._index_remotes[project] = list(get_remotes(index_remotes, remote_specs))
            self._storage_remotes[project] = list(get_remotes(storage_remotes, remote_specs))

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
            index_remotes = self._index_remotes[plugin._get_project()]
            storage_remotes = self._storage_remotes[plugin._get_project()]
            return index_remotes and storage_remotes

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
            index_remotes = self._index_remotes[plugin._get_project()]
            storage_remotes = self._storage_remotes[plugin._get_project()]
            return any(remote.spec.push for remote in index_remotes) and any(
                remote.spec.push for remote in storage_remotes
            )

    ################################################
    #               Local Private Methods          #
    ################################################

    # _create_remote_instances():
    #
    # Create the global set of Remote instances, including
    # project-specific and global instances, ensuring that all of them
    # are accessible.
    #
    # Args:
    #     on_failure (Callable[[Remote,Exception],None]):
    #     What do do when a remote doesn't respond.
    #
    # Returns:
    #    (Dict[RemoteSpec, AssetRemote], Dict[RemoteSpec, CASRemote]) -
    #    The created remote instances, index first, storage last.
    #
    def _create_remote_instances(self, *, on_failure=None):
        # Create a flat list of all remote specs, global or
        # project-specific
        remote_specs = self.global_remote_specs.copy()
        for project in self.project_remote_specs:
            remote_specs.extend(self.project_remote_specs[project])

        # By de-duplicating it after we flattened the list, we ensure
        # that we never instantiate the same remote twice. This
        # de-duplication also preserves their order.
        remote_specs = list(utils._deduplicate(remote_specs))

        # Now let's create a dict of this, indexed by their specs, so
        # that we can later assign them to the right projects.
        index_remotes = {}
        storage_remotes = {}
        for remote_spec in remote_specs:
            try:
                index, storage = self._instantiate_remote(remote_spec)
            except RemoteError as err:
                if on_failure:
                    on_failure(remote_spec, str(err))
                    continue

                raise

            # Finally, we can instantiate the remote. Note that
            # NamedTuples are hashable, so we can use them as pretty
            # low-overhead keys.
            if index:
                index_remotes[remote_spec] = index
            if storage:
                storage_remotes[remote_spec] = storage

        self._has_fetch_remotes = storage_remotes and index_remotes
        self._has_push_remotes = any(spec.push for spec in storage_remotes) and any(
            spec.push for spec in index_remotes
        )

        return index_remotes, storage_remotes

    # _instantiate_remote()
    #
    # Instantiate a remote given its spec, asserting that it is
    # reachable - this may produce two remote instances (a storage and
    # an index remote as specified by the class variables).
    #
    # Args:
    #
    #    remote_spec (RemoteSpec): The spec of the remote to
    #                              instantiate.
    #
    # Returns:
    #
    #    (Tuple[Remote|None, Remote|None]) - The remotes, index remote
    #    first, storage remote second. One must always be specified,
    #    the other may be None.
    #
    def _instantiate_remote(self, remote_spec):
        # Our remotes can be index, storage or both. In either case,
        # we need to use a different type of Remote for our calls, so
        # we create two objects here
        index = None
        storage = None
        if remote_spec.type in [RemoteType.INDEX, RemoteType.ALL]:
            index = AssetRemote(remote_spec)  # pylint: disable=not-callable
            index.check()
        if remote_spec.type in [RemoteType.STORAGE, RemoteType.ALL]:
            storage = CASRemote(remote_spec, self.cas)
            storage.check()

        return (index, storage)

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context.messenger.message(Message(message_type, message, **args))

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
        def remote_failed(remote, error):
            self._message(MessageType.WARN, "Failed to initialize remote {}: {}".format(remote.url, error))

        with self.context.messenger.timed_activity("Initializing remote caches", silent_nested=True):
            self.initialize_remotes(on_failure=remote_failed)

    # _list_refs_mtimes()
    #
    # List refs in a directory, given a base path. Also returns the
    # associated mtimes
    #
    # Args:
    #    base_path (str): Base path to traverse over
    #    glob_expr (str|None): Optional glob expression to match against files
    #
    # Returns:
    #     (iter (mtime, filename)]): iterator of tuples of mtime and refs
    #
    def _list_refs_mtimes(self, base_path, *, glob_expr=None):
        path = base_path
        if glob_expr is not None:
            globdir = os.path.dirname(glob_expr)
            if not any(c in "*?[" for c in globdir):
                # path prefix contains no globbing characters so
                # append the glob to optimise the os.walk()
                path = os.path.join(base_path, globdir)

        for root, _, files in os.walk(path):
            for filename in files:
                ref_path = os.path.join(root, filename)
                relative_path = os.path.relpath(ref_path, base_path)  # Relative to refs head
                if not glob_expr or fnmatch(relative_path, glob_expr):
                    # Obtain the mtime (the time a file was last modified)
                    yield (os.path.getmtime(ref_path), relative_path)

    # _remove_ref()
    #
    # Removes a ref.
    #
    # This also takes care of pruning away directories which can
    # be removed after having removed the given ref.
    #
    # Args:
    #    ref (str): The ref to remove
    #
    # Raises:
    #    (AssetCacheError): If the ref didnt exist, or a system error
    #                     occurred while removing it
    #
    def _remove_ref(self, ref):
        try:
            utils._remove_path_with_parents(self._basedir, ref)
        except FileNotFoundError as e:
            raise AssetCacheError("Could not find ref '{}'".format(ref)) from e
        except OSError as e:
            raise AssetCacheError("System error while removing ref '{}': {}".format(ref, e)) from e
