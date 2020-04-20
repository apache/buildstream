#
#  Copyright (C) 2017-2018 Codethink Limited
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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import grpc

from ._basecache import BaseCache
from ._cas.casremote import BlobNotFound
from ._exceptions import ArtifactError, CASError, CacheError, CASRemoteError, RemoteError
from ._protos.buildstream.v2 import buildstream_pb2, buildstream_pb2_grpc, artifact_pb2, artifact_pb2_grpc

from ._remote import BaseRemote
from . import utils


# ArtifactRemote():
#
# Facilitates communication with the BuildStream-specific part of
# artifact remotes.
#
class ArtifactRemote(BaseRemote):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.artifact_service = None

    def close(self):
        self.artifact_service = None
        super().close()

    # _configure_protocols():
    #
    # Configure the protocols used by this remote as part of the
    # remote initialization; Note that this should only be used in
    # Remote.init(), and is expected to fail when called by itself.
    #
    def _configure_protocols(self):
        # Set up artifact stub
        self.artifact_service = artifact_pb2_grpc.ArtifactServiceStub(self.channel)

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
        capabilities_service = buildstream_pb2_grpc.CapabilitiesStub(self.channel)

        # Check whether the server supports newer proto based artifact.
        try:
            request = buildstream_pb2.GetCapabilitiesRequest()
            if self.instance_name:
                request.instance_name = self.instance_name
            response = capabilities_service.GetCapabilities(request)
        except grpc.RpcError as e:
            # Check if this remote has the artifact service
            if e.code() == grpc.StatusCode.UNIMPLEMENTED:
                raise RemoteError(
                    "Configured remote does not have the BuildStream "
                    "capabilities service. Please check remote configuration."
                )
            # Else raise exception with details
            raise RemoteError("Remote initialisation failed: {}".format(e.details()))

        if not response.artifact_capabilities:
            raise RemoteError("Configured remote does not support artifact service")

        if self.spec.push and not response.artifact_capabilities.allow_updates:
            raise RemoteError("Artifact server does not allow push")

    # get_artifact():
    #
    # Get an artifact proto for a given cache key from the remote.
    #
    # Args:
    #    cache_key (str): The artifact cache key. NOTE: This "key"
    #                     is actually the ref/name and its name in
    #                     the protocol is inaccurate. You have been warned.
    #
    # Returns:
    #    (Artifact): The artifact proto
    #
    # Raises:
    #    grpc.RpcError: If someting goes wrong during the request.
    #
    def get_artifact(self, cache_key):
        artifact_request = artifact_pb2.GetArtifactRequest()
        artifact_request.cache_key = cache_key

        return self.artifact_service.GetArtifact(artifact_request)

    # update_artifact():
    #
    # Update an artifact with the given cache key on the remote with
    # the given proto.
    #
    # Args:
    #    cache_key (str): The artifact cache key of the artifact to update.
    #    artifact (ArtifactProto): The artifact proto to send.
    #
    # Raises:
    #     grpc.RpcError: If someting goes wrong during the request.
    #
    def update_artifact(self, cache_key, artifact):
        update_request = artifact_pb2.UpdateArtifactRequest()
        update_request.cache_key = cache_key
        update_request.artifact.CopyFrom(artifact)

        self.artifact_service.UpdateArtifact(update_request)


# An ArtifactCache manages artifacts.
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache(BaseCache):

    spec_name = "artifact_cache_specs"
    spec_error = ArtifactError
    config_node_name = "artifacts"
    index_remote_class = ArtifactRemote

    def __init__(self, context):
        super().__init__(context)

        # create artifact directory
        self._basedir = context.artifactdir
        os.makedirs(self._basedir, exist_ok=True)

    def update_mtime(self, ref):
        try:
            os.utime(os.path.join(self._basedir, ref))
        except FileNotFoundError as e:
            raise ArtifactError("Couldn't find artifact: {}".format(ref)) from e

    # preflight():
    #
    # Preflight check.
    #
    def preflight(self):
        self.cas.preflight()

    # contains():
    #
    # Check whether the artifact for the specified Element is already available
    # in the local artifact cache.
    #
    # Args:
    #     element (Element): The Element to check
    #     key (str): The cache key to use
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def contains(self, element, key):
        ref = element.get_artifact_name(key)

        return os.path.exists(os.path.join(self._basedir, ref))

    # list_artifacts():
    #
    # List artifacts in this cache in LRU order.
    #
    # Args:
    #     glob (str): An option glob expression to be used to list artifacts satisfying the glob
    #
    # Returns:
    #     ([str]) - A list of artifact names as generated in LRU order
    #
    def list_artifacts(self, *, glob=None):
        return [ref for _, ref in sorted(list(self._list_refs_mtimes(self._basedir, glob_expr=glob)))]

    # remove():
    #
    # Removes the artifact for the specified ref from the local
    # artifact cache.
    #
    # Args:
    #     ref (artifact_name): The name of the artifact to remove (as
    #                          generated by `Element.get_artifact_name`)
    #
    def remove(self, ref):
        try:
            self._remove_ref(ref)
        except CacheError as e:
            raise ArtifactError("{}".format(e)) from e

    # push():
    #
    # Push committed artifact to remote repository.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be pushed
    #     artifact (Artifact): The artifact being pushed
    #
    # Returns:
    #   (bool): True if any remote was updated, False if no pushes were required
    #
    # Raises:
    #   (ArtifactError): if there was an error
    #
    def push(self, element, artifact):
        project = element._get_project()
        display_key = element._get_brief_display_key()

        index_remotes = [r for r in self._index_remotes[project] if r.push]
        storage_remotes = [r for r in self._storage_remotes[project] if r.push]

        pushed = False
        # First push our files to all storage remotes, so that they
        # can perform file checks on their end
        for remote in storage_remotes:
            remote.init()
            element.status("Pushing data from artifact {} -> {}".format(display_key, remote))

            if self._push_artifact_blobs(artifact, remote):
                element.info("Pushed data from artifact {} -> {}".format(display_key, remote))
            else:
                element.info(
                    "Remote ({}) already has all data of artifact {} cached".format(
                        remote, element._get_brief_display_key()
                    )
                )

        for remote in index_remotes:
            remote.init()
            element.status("Pushing artifact {} -> {}".format(display_key, remote))

            if self._push_artifact_proto(element, artifact, remote):
                element.info("Pushed artifact {} -> {}".format(display_key, remote))
                pushed = True
            else:
                element.info(
                    "Remote ({}) already has artifact {} cached".format(remote, element._get_brief_display_key())
                )

        return pushed

    # pull():
    #
    # Pull artifact from one of the configured remote repositories.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be fetched
    #     key (str): The cache key to use
    #     pull_buildtrees (bool): Whether to pull buildtrees or not
    #
    # Returns:
    #   (bool): True if pull was successful, False if artifact was not available
    #
    def pull(self, element, key, *, pull_buildtrees=False):
        artifact = None
        display_key = key[: self.context.log_key_length]
        project = element._get_project()

        errors = []
        # Start by pulling our artifact proto, so that we know which
        # blobs to pull
        for remote in self._index_remotes[project]:
            remote.init()
            try:
                element.status("Pulling artifact {} <- {}".format(display_key, remote))
                artifact = self._pull_artifact_proto(element, key, remote)
                if artifact:
                    break

                element.info("Remote ({}) does not have artifact {} cached".format(remote, display_key))
            except CASError as e:
                element.warn("Could not pull from remote {}: {}".format(remote, e))
                errors.append(e)

        if errors and not artifact:
            raise ArtifactError(
                "Failed to pull artifact {}".format(display_key), detail="\n".join(str(e) for e in errors)
            )

        # If we don't have an artifact, we can't exactly pull our
        # artifact
        if not artifact:
            return False

        errors = []
        # If we do, we can pull it!
        for remote in self._storage_remotes[project]:
            remote.init()
            try:
                element.status("Pulling data for artifact {} <- {}".format(display_key, remote))

                if self._pull_artifact_storage(element, artifact, remote, pull_buildtrees=pull_buildtrees):
                    element.info("Pulled artifact {} <- {}".format(display_key, remote))
                    return True

                element.info("Remote ({}) does not have artifact {} cached".format(remote, display_key))
            except BlobNotFound as e:
                # Not all blobs are available on this remote
                element.info("Remote cas ({}) does not have blob {} cached".format(remote, e.blob))
                continue
            except CASError as e:
                element.warn("Could not pull from remote {}: {}".format(remote, e))
                errors.append(e)

        if errors:
            raise ArtifactError(
                "Failed to pull artifact {}".format(display_key), detail="\n".join(str(e) for e in errors)
            )

        return False

    # pull_tree():
    #
    # Pull a single Tree rather than an artifact.
    # Does not update local refs.
    #
    # Args:
    #     project (Project): The current project
    #     digest (Digest): The digest of the tree
    #
    def pull_tree(self, project, digest):
        for remote in self._storage_remotes[project]:
            digest = self.cas.pull_tree(remote, digest)

            if digest:
                # no need to pull from additional remotes
                return digest

        return None

    # push_message():
    #
    # Push the given protobuf message to all remotes.
    #
    # Args:
    #     project (Project): The current project
    #     message (Message): A protobuf message to push.
    #
    # Raises:
    #     (ArtifactError): if there was an error
    #
    def push_message(self, project, message):

        if self._has_push_remotes:
            push_remotes = [r for r in self._storage_remotes[project] if r.spec.push]
        else:
            push_remotes = []

        if not push_remotes:
            raise ArtifactError(
                "push_message was called, but no remote artifact " + "servers are configured as push remotes."
            )

        for remote in push_remotes:
            message_digest = remote.push_message(message)

        return message_digest

    # link_key():
    #
    # Add a key for an existing artifact.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be linked
    #     oldkey (str): An existing cache key for the artifact
    #     newkey (str): A new cache key for the artifact
    #
    def link_key(self, element, oldkey, newkey):
        oldref = element.get_artifact_name(oldkey)
        newref = element.get_artifact_name(newkey)

        if not os.path.exists(os.path.join(self._basedir, newref)):
            os.link(os.path.join(self._basedir, oldref), os.path.join(self._basedir, newref))

    # fetch_missing_blobs():
    #
    # Fetch missing blobs from configured remote repositories.
    #
    # Args:
    #     project (Project): The current project
    #     missing_blobs (list): The Digests of the blobs to fetch
    #
    def fetch_missing_blobs(self, project, missing_blobs):
        for remote in self._index_remotes[project]:
            if not missing_blobs:
                break

            remote.init()

            # fetch_blobs() will return the blobs that are still missing
            missing_blobs = self.cas.fetch_blobs(remote, missing_blobs, allow_partial=True)

        if missing_blobs:
            raise ArtifactError("Blobs not found on configured artifact servers")

    # find_missing_blobs():
    #
    # Find missing blobs from configured push remote repositories.
    #
    # Args:
    #     project (Project): The current project
    #     missing_blobs (list): The Digests of the blobs to check
    #
    # Returns:
    #     (list): The Digests of the blobs missing on at least one push remote
    #
    def find_missing_blobs(self, project, missing_blobs):
        if not missing_blobs:
            return []

        push_remotes = [r for r in self._storage_remotes[project] if r.spec.push]

        remote_missing_blobs_list = []

        for remote in push_remotes:
            remote.init()

            remote_missing_blobs = self.cas.remote_missing_blobs(remote, missing_blobs)

            for blob in remote_missing_blobs:
                if blob not in remote_missing_blobs_list:
                    remote_missing_blobs_list.append(blob)

        return remote_missing_blobs_list

    # check_remotes_for_element()
    #
    # Check if the element is available in any of the remotes
    #
    # Args:
    #    element (Element): The element to check
    #
    # Returns:
    #    (bool): True if the element is available remotely
    #
    def check_remotes_for_element(self, element):
        # If there are no remotes
        if not self._index_remotes:
            return False

        project = element._get_project()
        ref = element.get_artifact_name()
        for remote in self._index_remotes[project]:
            remote.init()

            if self._query_remote(ref, remote):
                return True

        return False

    ################################################
    #             Local Private Methods            #
    ################################################

    # _push_artifact_blobs()
    #
    # Push the blobs that make up an artifact to the remote server.
    #
    # Args:
    #    artifact (Artifact): The artifact whose blobs to push.
    #    remote (CASRemote): The remote to push the blobs to.
    #
    # Returns:
    #    (bool) - True if we uploaded anything, False otherwise.
    #
    # Raises:
    #    ArtifactError: If we fail to push blobs (*unless* they're
    #    already there or we run out of space on the server).
    #
    def _push_artifact_blobs(self, artifact, remote):
        artifact_proto = artifact._get_proto()

        try:
            if str(artifact_proto.files):
                self.cas._send_directory(remote, artifact_proto.files)

            if str(artifact_proto.buildtree):
                try:
                    self.cas._send_directory(remote, artifact_proto.buildtree)
                except FileNotFoundError:
                    pass

            digests = []
            if str(artifact_proto.public_data):
                digests.append(artifact_proto.public_data)

            for log_file in artifact_proto.logs:
                digests.append(log_file.digest)

            self.cas.send_blobs(remote, digests)

        except CASRemoteError as cas_error:
            if cas_error.reason != "cache-too-full":
                raise ArtifactError("Failed to push artifact blobs: {}".format(cas_error))
            return False
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise ArtifactError("Failed to push artifact blobs: {}".format(e.details()))
            return False

        return True

    # _push_artifact_proto()
    #
    # Pushes the artifact proto to remote.
    #
    # Args:
    #    element (Element): The element
    #    artifact (Artifact): The related artifact being pushed
    #    remote (ArtifactRemote): Remote to push to
    #
    # Returns:
    #    (bool): Whether we pushed the artifact.
    #
    # Raises:
    #    ArtifactError: If the push fails for any reason except the
    #    artifact already existing.
    #
    def _push_artifact_proto(self, element, artifact, remote):

        artifact_proto = artifact._get_proto()

        keys = list(utils._deduplicate([artifact_proto.strong_key, artifact_proto.weak_key]))

        # Check whether the artifact is on the server
        for key in keys:
            try:
                remote.get_artifact(element.get_artifact_name(key=key))
            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.NOT_FOUND:
                    raise ArtifactError("Error checking artifact cache: {}".format(e.details()))
            else:
                return False

        # If not, we send the artifact proto
        for key in keys:
            try:
                remote.update_artifact(element.get_artifact_name(key=key), artifact_proto)
            except grpc.RpcError as e:
                raise ArtifactError("Failed to push artifact: {}".format(e.details()))

        return True

    # _pull_artifact_storage():
    #
    # Pull artifact blobs from the given remote.
    #
    # Args:
    #    element (Element): element to pull
    #    key (str): The specific key for the artifact to pull
    #    remote (CASRemote): remote to pull from
    #    pull_buildtree (bool): whether to pull buildtrees or not
    #
    # Returns:
    #    (bool): True if we pulled any blobs.
    #
    # Raises:
    #    ArtifactError: If the pull failed for any reason except the
    #    blobs not existing on the server.
    #
    def _pull_artifact_storage(self, element, artifact, remote, pull_buildtrees=False):
        def __pull_digest(digest):
            self.cas._fetch_directory(remote, digest)
            required_blobs = self.cas.required_blobs_for_directory(digest)
            missing_blobs = self.cas.local_missing_blobs(required_blobs)
            if missing_blobs:
                self.cas.fetch_blobs(remote, missing_blobs)

        try:
            if str(artifact.files):
                __pull_digest(artifact.files)

            if pull_buildtrees and str(artifact.buildtree):
                __pull_digest(artifact.buildtree)

            digests = []
            if str(artifact.public_data):
                digests.append(artifact.public_data)

            for log_digest in artifact.logs:
                digests.append(log_digest.digest)

            self.cas.fetch_blobs(remote, digests)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise ArtifactError("Failed to pull artifact: {}".format(e.details()))
            return False

        return True

    # _pull_artifact_proto():
    #
    # Pull an artifact proto from a remote server.
    #
    # Args:
    #    element (Element): The element whose artifact to pull.
    #    key (str): The specific key for the artifact to pull.
    #    remote (ArtifactRemote): The remote to pull from.
    #
    # Returns:
    #    (Artifact|None): The artifact proto, or None if the server
    #    doesn't have it.
    #
    # Raises:
    #    ArtifactError: If the pull fails.
    #
    def _pull_artifact_proto(self, element, key, remote):
        artifact_name = element.get_artifact_name(key=key)

        try:
            artifact = remote.get_artifact(artifact_name)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise ArtifactError("Failed to pull artifact: {}".format(e.details()))
            return None

        # Write the artifact proto to cache
        artifact_path = os.path.join(self._basedir, artifact_name)
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        with utils.save_file_atomic(artifact_path, mode="wb") as f:
            f.write(artifact.SerializeToString())

        return artifact

    # _query_remote()
    #
    # Args:
    #    ref (str): The artifact ref
    #    remote (ArtifactRemote): The remote we want to check
    #
    # Returns:
    #    (bool): True if the ref exists in the remote, False otherwise.
    #
    def _query_remote(self, ref, remote):
        request = artifact_pb2.GetArtifactRequest()
        request.cache_key = ref
        try:
            remote.artifact_service.GetArtifact(request)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise ArtifactError("Error when querying: {}".format(e.details()))
            return False

        return True
