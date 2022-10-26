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

from ._cas.casremote import BlobNotFound
from .storage._casbaseddirectory import CasBasedDirectory
from ._assetcache import AssetCache
from ._exceptions import CASError, CASRemoteError, SourceCacheError, AssetCacheError
from . import utils
from ._protos.buildstream.v2 import source_pb2

REMOTE_ASSET_SOURCE_URN_TEMPLATE = "urn:fdc:buildstream.build:2020:source:{}"


# Class that keeps config of remotes and deals with caching of sources.
#
# Args:
#    context (Context): The Buildstream context
#
class SourceCache(AssetCache):
    def __init__(self, context):
        super().__init__(context)

        self._basedir = os.path.join(context.cachedir, "source_protos")
        os.makedirs(self._basedir, exist_ok=True)

    # contains()
    #
    # Given a source, gets the ref name and checks whether the local CAS
    # contains it.
    #
    # Args:
    #    source (Source): Source to check
    #
    # Returns:
    #    (bool): whether the CAS contains this source or not
    #
    def contains(self, source):
        ref = source._get_source_name()
        path = self._source_path(ref)

        if not os.path.exists(path):
            return False

        # check files
        source_proto = self._get_source(ref)
        return self.cas.contains_directory(source_proto.files, with_files=True)

    # commit()
    #
    # Given a source, it stages and commits it to the local CAS.
    #
    # Args:
    #    source: last source
    def commit(self, source):
        ref = source._get_source_name()

        vdir = CasBasedDirectory(self.cas)

        if not source.BST_STAGE_VIRTUAL_DIRECTORY:
            with utils._tempdir(dir=self.context.tmpdir, prefix="staging-temp") as tmpdir:
                source._stage(tmpdir)
                vdir.import_files(tmpdir, collect_result=False)
        else:
            source._stage(vdir)

        self._store_source(ref, vdir._get_digest())

    # export()
    #
    # Exports a source in the CAS to a virtual directory
    #
    # Args:
    #    source (Source): source we want to export
    #
    # Returns:
    #    CASBasedDirectory
    def export(self, source):
        ref = source._get_source_name()
        source = self._get_source(ref)
        return CasBasedDirectory(self.cas, digest=source.files)

    # pull()
    #
    # Attempts to pull sources from configure remote source caches.
    #
    # Args:
    #    source (Source): The source we want to fetch
    #    progress (callable|None): The progress callback
    #
    # Returns:
    #    (bool): True if pull successful, False if not
    def pull(self, source):
        ref = source._get_source_name()
        project = source._get_project()
        display_key = source._get_brief_display_key()

        index_remotes, storage_remotes = self.get_remotes(project.name, False)

        # First fetch the source directory digest so we know what to pull
        source_digest = None
        for remote in index_remotes:
            remote.init()
            source.status("Pulling source {} <- {}".format(display_key, remote))

            source_digest = self._pull_source(ref, remote)
            if source_digest is None:
                source.info("Remote source service ({}) does not have source {} cached".format(remote, display_key))
                continue

        if not source_digest:
            return False

        for remote in storage_remotes:
            remote.init()
            source.status("Pulling data for source {} <- {}".format(display_key, remote))

            try:
                # Fetch source blobs
                self.cas._fetch_directory(remote, source_digest)

                source.info("Pulled source {} <- {}".format(display_key, remote))
                return True
            except BlobNotFound as e:
                # Not all blobs are available on this remote
                source.info("Remote cas ({}) does not have blob {} cached".format(remote, e.blob))
                continue
            except CASError as e:
                raise SourceCacheError("Failed to pull source {}: {}".format(display_key, e), temporary=True) from e

        return False

    # push()
    #
    # Push a source to configured remote source caches
    #
    # Args:
    #    source (Source): source to push
    #
    # Returns:
    #    (Bool): whether it pushed to a remote source cache
    #
    def push(self, source):
        ref = source._get_source_name()
        project = source._get_project()

        index_remotes, storage_remotes = self.get_remotes(project.name, True)

        pushed_storage = False
        pushed_index = False

        display_key = source._get_brief_display_key()
        for remote in storage_remotes:
            remote.init()
            source.status("Pushing data for source {} -> {}".format(display_key, remote))

            source_proto = self._get_source(ref)
            try:
                self.cas._send_directory(remote, source_proto.files)
                pushed_storage = True
            except CASRemoteError:
                source.info("Failed to push source files {} -> {}".format(display_key, remote))
                continue

        for remote in index_remotes:
            remote.init()
            source.status("Pushing source {} -> {}".format(display_key, remote))

            # check whether cache has files already
            if self._pull_source(ref, remote) is not None:
                source.info("Remote ({}) already has source {} cached".format(remote, display_key))
                continue

            if not self._push_source(ref, remote):
                source.info("Failed to push source metadata {} -> {}".format(display_key, remote))
                continue

            source.info("Pushed source {} -> {}".format(display_key, remote))
            pushed_index = True

        return pushed_index and pushed_storage

    def _store_source(self, ref, digest):
        source_proto = source_pb2.Source()
        source_proto.files.CopyFrom(digest)

        self._store_proto(source_proto, ref)

    def _store_proto(self, proto, ref):
        path = self._source_path(ref)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with utils.save_file_atomic(path, "w+b") as f:
            f.write(proto.SerializeToString())

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

    def _pull_source(self, source_ref, remote):
        uri = REMOTE_ASSET_SOURCE_URN_TEMPLATE.format(source_ref)

        remote.init()
        try:
            response = remote.fetch_directory([uri])
        except AssetCacheError as e:
            raise SourceCacheError("Failed to pull source: {}".format(e), temporary=True) from e

        if response:
            self._store_source(source_ref, response.root_directory_digest)
            return response.root_directory_digest

        return None

    def _push_source(self, source_ref, remote):
        uri = REMOTE_ASSET_SOURCE_URN_TEMPLATE.format(source_ref)

        remote.init()
        source_proto = self._get_source(source_ref)
        try:
            remote.push_directory([uri], source_proto.files)
        except AssetCacheError as e:
            raise SourceCacheError("Failed to push source: {}".format(e), temporary=True) from e

        return True
