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
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#
import os
import re
from typing import List, Dict, Tuple, Iterable, Optional
import grpc

from . import utils
from ._cas import CASRemote, CASCache
from ._exceptions import AssetCacheError, RemoteError
from ._remotespec import RemoteSpec, RemoteType
from ._remote import BaseRemote
from ._protos.build.bazel.remote.asset.v1 import remote_asset_pb2, remote_asset_pb2_grpc
from ._protos.google.rpc import code_pb2


class AssetRemote(BaseRemote):
    def __init__(self, spec):
        super().__init__(spec)
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
        if self.spec.instance_name:
            request.instance_name = self.spec.instance_name

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
            if self.spec.instance_name:
                request.instance_name = self.spec.instance_name

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
        if self.spec.instance_name:
            request.instance_name = self.spec.instance_name
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
        if self.spec.instance_name:
            request.instance_name = self.spec.instance_name
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
        if self.spec.instance_name:
            request.instance_name = self.spec.instance_name
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
        if self.spec.instance_name:
            request.instance_name = self.spec.instance_name
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


# RemotePair()
#
# A pair of remotes which corresponds to a RemoteSpec, we
# need separate remote objects for the index and the storage so
# we store them together for each RemoteSpec here.
#
# Either members of the RemotePair may be None, in case that
# the user specified a diffrerent RemoteSpec for indexing and
# for storage.
#
# Both members may also be None, in the case that we were unable
# to establish a connection to this remote at initialization time.
#
class RemotePair:
    def __init__(self, cas: CASCache, spec: RemoteSpec):
        self.index: Optional[AssetRemote] = None
        self.storage: Optional[CASRemote] = None
        self.error: Optional[str] = None

        try:
            if spec.remote_type in [RemoteType.INDEX, RemoteType.ALL]:
                index = AssetRemote(spec)
                index.check()
                self.index = index
            if spec.remote_type in [RemoteType.STORAGE, RemoteType.ALL]:
                storage = CASRemote(spec, cas)
                storage.check()
                self.storage = storage
        except RemoteError as e:
            self.error = str(e)


# Base Asset Cache for Caches to derive from
#
class AssetCache:
    def __init__(self, context):
        self.context = context
        self.cas: CASCache = context.get_cascache()

        # Table of RemotePair objects
        self._remotes: Dict[RemoteSpec, RemotePair] = {}

        # Table of prioritized RemoteSpecs which are valid for each project
        self._project_specs: Dict[str, List[RemoteSpec]] = {}

        self._has_fetch_remotes: bool = False
        self._has_push_remotes: bool = False

        self._basedir = None

    # release_resources():
    #
    # Release resources used by AssetCache.
    #
    def release_resources(self):

        # Close all remotes and their gRPC channels
        for remote in self._remotes.values():
            if remote.index:
                remote.index.close()
            if remote.storage:
                remote.storage.close()

    # setup_remotes():
    #
    # Sets up which remotes to use
    #
    # Args:
    #    specs: The active remote specs
    #    project_specs: List of specs for each project
    #
    def setup_remotes(self, specs: Iterable[RemoteSpec], project_specs: Dict[str, List[RemoteSpec]]):

        # Hold on to the project specs
        self._project_specs = project_specs

        for spec in specs:
            # This can be called multiple times, ensure that we only try
            # to instantiate each remote once.
            #
            if spec in self._remotes:
                continue

            remote = RemotePair(self.cas, spec)
            if remote.error:
                self.context.messenger.warn("Failed to initialize remote {}: {}".format(spec.url, remote.error))

            self._remotes[spec] = remote

        # Determine overall existance of push or fetch remotes
        self._has_fetch_remotes = any(remote.storage for _, remote in self._remotes.items()) and any(
            remote.index for _, remote in self._remotes.items()
        )
        self._has_push_remotes = any(spec.push and remote.storage for spec, remote in self._remotes.items()) and any(
            spec.push and remote.index for spec, remote in self._remotes.items()
        )

    # get_remotes():
    #
    # List the index remotes and storage remotes available for fetching
    #
    # Args:
    #    project_name: The project name
    #    push: Whether pushing is required for this remote
    #
    # Returns:
    #    index_remotes: The index remotes
    #    storage_remotes: The storage remotes
    #
    def get_remotes(self, project_name: str, push: bool) -> Tuple[List[AssetRemote], List[CASRemote]]:
        try:
            project_specs = self._project_specs[project_name]
        except KeyError:
            # Technically this shouldn't happen, but here is a defensive return none the less.
            return [], []

        index_remotes = []
        storage_remotes = []
        for spec in project_specs:

            if push and not spec.push:
                continue

            remote = self._remotes[spec]
            if remote.index:
                index_remotes.append(remote.index)
            if remote.storage:
                storage_remotes.append(remote.storage)

        return index_remotes, storage_remotes

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
            project = plugin._get_project()
            index_remotes, storage_remotes = self.get_remotes(project.name, False)

            # Check whether the specified element's project has fetch remotes
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
            project = plugin._get_project()
            index_remotes, storage_remotes = self.get_remotes(project.name, True)

            # Check whether the specified element's project has fetch remotes
            return bool(index_remotes and storage_remotes)

    # list_refs_mtimes()
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
    def list_refs_mtimes(self, base_path, *, glob_expr=None):
        path = base_path
        if glob_expr is not None:
            globdir = os.path.dirname(glob_expr)
            if not any(c in "*?[" for c in globdir):
                # path prefix contains no globbing characters so
                # append the glob to optimise the os.walk()
                path = os.path.join(base_path, globdir)

        regexer = None
        if glob_expr:
            expression = utils._glob2re(glob_expr)
            regexer = re.compile(expression)

        for root, _, files in os.walk(path):
            for filename in files:
                ref_path = os.path.join(root, filename)
                relative_path = os.path.relpath(ref_path, base_path)  # Relative to refs head
                if regexer is None or regexer.match(relative_path):
                    # Obtain the mtime (the time a file was last modified)
                    yield (os.path.getmtime(ref_path), relative_path)

    # remove_ref()
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
    def remove_ref(self, ref):
        try:
            utils._remove_path_with_parents(self._basedir, ref)
        except FileNotFoundError as e:
            raise AssetCacheError("Could not find ref '{}'".format(ref)) from e
        except OSError as e:
            raise AssetCacheError("System error while removing ref '{}': {}".format(ref, e)) from e
