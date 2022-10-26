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
import os
import grpc

from ._cas.casremote import BlobNotFound
from ._assetcache import AssetCache
from ._exceptions import AssetCacheError, CASError, CASRemoteError, SourceCacheError
from . import utils
from ._protos.buildstream.v2 import source_pb2

REMOTE_ASSET_SOURCE_URN_TEMPLATE = "urn:fdc:buildstream.build:2020:source:{}"


# Class that keeps config of remotes and deals with caching of sources.
#
# Args:
#    context (Context): The Buildstream context
#
class ElementSourcesCache(AssetCache):
    def __init__(self, context):
        super().__init__(context)

        self._basedir = os.path.join(context.cachedir, "elementsources")
        os.makedirs(self._basedir, exist_ok=True)

    # load_proto():
    #
    # Load source proto from local cache.
    #
    # Args:
    #    sources (ElementSources): The sources whose proto we want to load
    #
    def load_proto(self, sources):
        ref = sources.get_cache_key()
        path = self._source_path(ref)

        if not os.path.exists(path):
            return None

        source_proto = source_pb2.Source()
        with open(path, "r+b") as f:
            source_proto.ParseFromString(f.read())
            return source_proto

    def store_proto(self, sources, proto):
        ref = sources.get_cache_key()
        path = self._source_path(ref)

        with utils.save_file_atomic(path, "w+b") as f:
            f.write(proto.SerializeToString())

    # pull():
    #
    # Attempts to pull sources from configured remote source caches.
    #
    # Args:
    #    sources (ElementSources): The sources we want to fetch
    #
    # Returns:
    #    (bool): True if pull successful, False if not
    #
    def pull(self, sources, plugin):
        project = sources.get_project()

        ref = sources.get_cache_key()
        display_key = sources.get_brief_display_key()

        uri = REMOTE_ASSET_SOURCE_URN_TEMPLATE.format(ref)

        index_remotes, storage_remotes = self.get_remotes(project.name, False)

        source_digest = None
        errors = []
        # Start by pulling our source proto, so that we know which
        # blobs to pull
        for remote in index_remotes:
            remote.init()
            try:
                plugin.status("Pulling source {} <- {}".format(display_key, remote))
                response = remote.fetch_blob([uri])
                if response:
                    source_digest = response.blob_digest
                    break

                plugin.info("Remote ({}) does not have source {} cached".format(remote, display_key))
            except AssetCacheError as e:
                plugin.warn("Could not pull from remote {}: {}".format(remote, e))
                errors.append(e)

        if errors and not source_digest:
            raise SourceCacheError(
                "Failed to pull source {}".format(display_key),
                detail="\n".join(str(e) for e in errors),
                temporary=True,
            )

        # If we don't have a source proto, we can't pull source files
        if not source_digest:
            return False

        errors = []
        for remote in storage_remotes:
            remote.init()
            try:
                plugin.status("Pulling data for source {} <- {}".format(display_key, remote))

                if self._pull_source_storage(ref, source_digest, remote):
                    plugin.info("Pulled source {} <- {}".format(display_key, remote))
                    return True

                plugin.info("Remote ({}) does not have source {} cached".format(remote, display_key))
            except BlobNotFound as e:
                # Not all blobs are available on this remote
                plugin.info("Remote cas ({}) does not have blob {} cached".format(remote, e.blob))
                continue
            except CASError as e:
                plugin.warn("Could not pull from remote {}: {}".format(remote, e))
                errors.append(e)

        if errors:
            raise SourceCacheError(
                "Failed to pull source {}".format(display_key), detail="\n".join(str(e) for e in errors)
            )

        return False

    # push():
    #
    # Push sources to remote repository.
    #
    # Args:
    #    sources (ElementSources): The sources to be pushed
    #
    # Returns:
    #   (bool): True if any remote was updated, False if no pushes were required
    #
    # Raises:
    #   (SourceCacheError): if there was an error
    #
    def push(self, sources, plugin):
        project = sources.get_project()

        ref = sources.get_cache_key()
        display_key = sources.get_brief_display_key()

        uri = REMOTE_ASSET_SOURCE_URN_TEMPLATE.format(ref)

        index_remotes, storage_remotes = self.get_remotes(project.name, True)

        source_proto = self.load_proto(sources)
        source_digest = self.cas.add_object(buffer=source_proto.SerializeToString())

        pushed = False

        # First push our files to all storage remotes, so that they
        # can perform file checks on their end
        for remote in storage_remotes:
            remote.init()
            plugin.status("Pushing data from source {} -> {}".format(display_key, remote))

            if self._push_source_blobs(source_proto, source_digest, remote):
                plugin.info("Pushed data from source {} -> {}".format(display_key, remote))
            else:
                plugin.info("Remote ({}) already has all data of source {} cached".format(remote, display_key()))

        for remote in index_remotes:
            remote.init()
            plugin.status("Pushing source {} -> {}".format(display_key, remote))

            if self._push_source_proto(uri, source_proto, source_digest, remote):
                plugin.info("Pushed source {} -> {}".format(display_key, remote))
                pushed = True
            else:
                plugin.info("Remote ({}) already has source {} cached".format(remote, display_key))

        return pushed

    def _get_source(self, ref):
        path = self._source_path(ref)
        source_proto = source_pb2.Source()
        try:
            with open(path, "r+b") as f:
                source_proto.ParseFromString(f.read())
                return source_proto
        except FileNotFoundError as e:
            raise SourceCacheError("Attempted to access unavailable source: {}".format(e)) from e

    def _source_path(self, ref):
        return os.path.join(self._basedir, ref)

    # _push_source_blobs()
    #
    # Push the blobs that make up an source to the remote server.
    #
    # Args:
    #    source_proto: The source proto whose blobs to push.
    #    source_digest: The digest of the source proto.
    #    remote (CASRemote): The remote to push the blobs to.
    #
    # Returns:
    #    (bool) - True if we uploaded anything, False otherwise.
    #
    # Raises:
    #    SourceCacheError: If we fail to push blobs (*unless* they're
    #    already there or we run out of space on the server).
    #
    def _push_source_blobs(self, source_proto, source_digest, remote):
        try:
            # Push source files
            self.cas._send_directory(remote, source_proto.files)
            # Push source proto
            self.cas.send_blobs(remote, [source_digest])

        except CASRemoteError as cas_error:
            if cas_error.reason != "cache-too-full":
                raise SourceCacheError("Failed to push source blobs: {}".format(cas_error))
            return False
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise SourceCacheError(
                    "Failed to push source blobs with status {}: {}".format(e.code().name, e.details()), temporary=True
                )
            return False

        return True

    # _push_source_proto()
    #
    # Pushes the source proto to remote.
    #
    # Args:
    #    source_proto: The source proto.
    #    source_digest: The digest of the source proto.
    #    remote (AssetRemote): Remote to push to
    #
    # Returns:
    #    (bool): Whether we pushed the source.
    #
    # Raises:
    #    SourceCacheError: If the push fails for any reason except the
    #    source already existing.
    #
    def _push_source_proto(self, uri, source_proto, source_digest, remote):
        try:
            response = remote.fetch_blob([uri])
            # Skip push if source is already on the server
            if response and response.blob_digest == source_digest:
                return False
        except AssetCacheError as e:
            raise SourceCacheError("Error checking source cache: {}".format(e), temporary=True) from e

        referenced_directories = [source_proto.files]

        try:
            remote.push_blob(
                [uri],
                source_digest,
                references_directories=referenced_directories,
            )
        except grpc.RpcError as e:
            raise SourceCacheError(
                "Failed to push source with status {}: {}".format(e.code().name, e.details()), temporary=True
            )

        return True

    # _pull_source_storage():
    #
    # Pull source blobs from the given remote.
    #
    # Args:
    #    key (str): The specific key for the source to pull
    #    remote (CASRemote): remote to pull from
    #
    # Returns:
    #    (bool): True if we pulled any blobs.
    #
    # Raises:
    #    SourceCacheError: If the pull failed for any reason except the
    #    blobs not existing on the server.
    #
    def _pull_source_storage(self, key, source_digest, remote):
        try:
            # Fetch and parse source proto
            self.cas.fetch_blobs(remote, [source_digest])
            source = source_pb2.Source()
            with self.cas.open(source_digest, "rb") as f:
                source.ParseFromString(f.read())

            # Write the source proto to cache
            source_path = os.path.join(self._basedir, key)
            with utils.save_file_atomic(source_path, mode="wb") as f:
                f.write(source.SerializeToString())

            self.cas._fetch_directory(remote, source.files)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise SourceCacheError(
                    "Failed to pull source with status {}: {}".format(e.code().name, e.details()), temporary=True
                )
            return False

        return True

    def _push_source(self, source_ref, remote):
        uri = REMOTE_ASSET_SOURCE_URN_TEMPLATE.format(source_ref)

        try:
            remote.init()
            source_proto = self._get_source(source_ref)
            remote.push_directory([uri], source_proto.files)
            return True

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise SourceCacheError(
                    "Failed to push source with status {}: {}".format(e.code().name, e.details()), temporary=True
                )
            return False
