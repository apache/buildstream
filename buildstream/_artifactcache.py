#
#  Copyright (C) 2017-2018 Codethink Limited
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
from .types import _KeyStrength
from ._exceptions import ArtifactError, CASError, CASCacheError
from ._protos.buildstream.v2 import artifact_pb2, artifact_pb2_grpc

from ._cas import CASRemoteSpec
from .storage._casbaseddirectory import CasBasedDirectory
from ._artifact import Artifact


# An ArtifactCacheSpec holds the user configuration for a single remote
# artifact cache.
#
# Args:
#     url (str): Location of the remote artifact cache
#     push (bool): Whether we should attempt to push artifacts to this cache,
#                  in addition to pulling from it.
#
class ArtifactCacheSpec(CASRemoteSpec):
    pass


# An ArtifactCache manages artifacts.
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache(BaseCache):

    spec_class = ArtifactCacheSpec
    spec_name = "artifact_cache_specs"
    spec_error = ArtifactError
    config_node_name = "artifacts"

    def __init__(self, context):
        super().__init__(context)

        self._required_elements = set()       # The elements required for this session

        # create artifact directory
        self.artifactdir = context.artifactdir
        os.makedirs(self.artifactdir, exist_ok=True)

        self.casquota.add_remove_callbacks(self.unrequired_artifacts, self.remove)
        self.casquota.add_list_refs_callback(self.list_artifacts)

        self.cas.add_reachable_directories_callback(self._reachable_directories)
        self.cas.add_reachable_digests_callback(self._reachable_digests)

    # mark_required_elements():
    #
    # Mark elements whose artifacts are required for the current run.
    #
    # Artifacts whose elements are in this list will be locked by the artifact
    # cache and not touched for the duration of the current pipeline.
    #
    # Args:
    #     elements (iterable): A set of elements to mark as required
    #
    def mark_required_elements(self, elements):

        # We risk calling this function with a generator, so we
        # better consume it first.
        #
        elements = list(elements)

        # Mark the elements as required. We cannot know that we know the
        # cache keys yet, so we only check that later when deleting.
        #
        self._required_elements.update(elements)

        # For the cache keys which were resolved so far, we bump
        # the mtime of them.
        #
        # This is just in case we have concurrent instances of
        # BuildStream running with the same artifact cache, it will
        # reduce the likelyhood of one instance deleting artifacts
        # which are required by the other.
        for element in elements:
            strong_key = element._get_cache_key(strength=_KeyStrength.STRONG)
            weak_key = element._get_cache_key(strength=_KeyStrength.WEAK)
            for key in (strong_key, weak_key):
                if key:
                    ref = element.get_artifact_name(key)

                    try:
                        self.update_mtime(ref)
                    except ArtifactError:
                        pass

    def update_mtime(self, ref):
        try:
            os.utime(os.path.join(self.artifactdir, ref))
        except FileNotFoundError as e:
            raise ArtifactError("Couldn't find artifact: {}".format(ref)) from e

    # unrequired_artifacts()
    #
    # Returns iterator over artifacts that are not required in the build plan
    #
    # Returns:
    #     (iter): Iterator over tuples of (float, str) where float is the time
    #             and str is the artifact ref
    #
    def unrequired_artifacts(self):
        required_artifacts = set(map(lambda x: x.get_artifact_name(),
                                     self._required_elements))
        for (mtime, artifact) in self._list_refs_mtimes(self.artifactdir):
            if artifact not in required_artifacts:
                yield (mtime, artifact)

    def required_artifacts(self):
        # Build a set of the cache keys which are required
        # based on the required elements at cleanup time
        #
        # We lock both strong and weak keys - deleting one but not the
        # other won't save space, but would be a user inconvenience.
        for element in self._required_elements:
            yield element._get_cache_key(strength=_KeyStrength.STRONG)
            yield element._get_cache_key(strength=_KeyStrength.WEAK)

    def full(self):
        return self.casquota.full()

    # add_artifact_size()
    #
    # Adds the reported size of a newly cached artifact to the
    # overall estimated size.
    #
    # Args:
    #     artifact_size (int): The size to add.
    #
    def add_artifact_size(self, artifact_size):
        cache_size = self.casquota.get_cache_size()
        cache_size += artifact_size

        self.casquota.set_cache_size(cache_size)

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

        return os.path.exists(os.path.join(self.artifactdir, ref))

    # contains_subdir_artifact():
    #
    # Check whether an artifact element contains a digest for a subdir
    # which is populated in the cache, i.e non dangling.
    #
    # Args:
    #     element (Element): The Element to check
    #     key (str): The cache key to use
    #     subdir (str): The subdir to check
    #     with_files (bool): Whether to check files as well
    #
    # Returns: True if the subdir exists & is populated in the cache, False otherwise
    #
    def contains_subdir_artifact(self, element, key, subdir, *, with_files=True):
        ref = element.get_artifact_name(key)
        return self.cas.contains_subdir_artifact(ref, subdir, with_files=with_files)

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
        return [ref for _, ref in sorted(list(self._list_refs_mtimes(self.artifactdir, glob_expr=glob)))]

    # remove():
    #
    # Removes the artifact for the specified ref from the local
    # artifact cache.
    #
    # Args:
    #     ref (artifact_name): The name of the artifact to remove (as
    #                          generated by `Element.get_artifact_name`)
    #     defer_prune (bool): Optionally declare whether pruning should
    #                         occur immediately after the ref is removed.
    #
    # Returns:
    #    (int): The amount of space recovered in the cache, in bytes
    #
    def remove(self, ref, *, defer_prune=False):
        try:
            return self.cas.remove(ref, basedir=self.artifactdir, defer_prune=defer_prune)
        except CASCacheError as e:
            raise ArtifactError("{}".format(e)) from e

    # prune():
    #
    # Prune the artifact cache of unreachable refs
    #
    def prune(self):
        return self.cas.prune()

    # diff():
    #
    # Return a list of files that have been added or modified between
    # the artifacts described by key_a and key_b.
    #
    # Args:
    #     element (Element): The element whose artifacts to compare
    #     key_a (str): The first artifact key
    #     key_b (str): The second artifact key
    #
    def diff(self, element, key_a, key_b, *, subdir=None):
        context = self.context
        artifact_a = Artifact(element, context, strong_key=key_a)
        artifact_b = Artifact(element, context, strong_key=key_b)
        digest_a = artifact_a._get_proto().files
        digest_b = artifact_b._get_proto().files

        added = []
        removed = []
        modified = []

        self.cas.diff_trees(digest_a, digest_b, added=added, removed=removed, modified=modified)

        return modified, removed, added

    # push():
    #
    # Push committed artifact to remote repository.
    #
    # Args:
    #     element (Element): The Element whose artifact is to be pushed
    #     keys (list): The cache keys to use
    #
    # Returns:
    #   (bool): True if any remote was updated, False if no pushes were required
    #
    # Raises:
    #   (ArtifactError): if there was an error
    #
    def push(self, element, artifact=None):
        project = element._get_project()

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        pushed = False

        # An Artifact instance will have been passed if called via Element,
        # only needs to be instantiated if invoked externally.
        if artifact is None:
            context = self.context
            artifact = Artifact(element, context, strong_key=element._get_cache_key())

        for remote in push_remotes:
            remote.init()
            display_key = element._get_brief_display_key()
            element.status("Pushing artifact {} -> {}".format(display_key, remote.spec.url))

            if self._push_artifact(element, artifact, remote):
                element.info("Pushed artifact {} -> {}".format(display_key, remote.spec.url))
                pushed = True
            else:
                element.info("Remote ({}) already has artifact {} cached".format(
                    remote.spec.url, element._get_brief_display_key()
                ))

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
        display_key = key[:self.context.log_key_length]
        project = element._get_project()

        for remote in self._remotes[project]:
            remote.init()
            try:
                element.status("Pulling artifact {} <- {}".format(display_key, remote.spec.url))

                if self._pull_artifact(element, key, remote, pull_buildtrees=pull_buildtrees):
                    element.info("Pulled artifact {} <- {}".format(display_key, remote.spec.url))
                    # no need to pull from additional remotes
                    return True
                else:
                    element.info("Remote ({}) does not have artifact {} cached".format(
                        remote.spec.url, display_key
                    ))

            except CASError as e:
                raise ArtifactError("Failed to pull artifact {}: {}".format(
                    display_key, e)) from e

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
        for remote in self._remotes[project]:
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
            push_remotes = [r for r in self._remotes[project] if r.spec.push]
        else:
            push_remotes = []

        if not push_remotes:
            raise ArtifactError("push_message was called, but no remote artifact " +
                                "servers are configured as push remotes.")

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

        if not os.path.exists(os.path.join(self.artifactdir, newref)):
            os.link(os.path.join(self.artifactdir, oldref),
                    os.path.join(self.artifactdir, newref))

    # get_artifact_logs():
    #
    # Get the logs of an existing artifact
    #
    # Args:
    #     ref (str): The ref of the artifact
    #
    # Returns:
    #     logsdir (CasBasedDirectory): A CasBasedDirectory containing the artifact's logs
    #
    def get_artifact_logs(self, ref):
        cache_id = self.cas.resolve_ref(ref, update_mtime=True)
        vdir = CasBasedDirectory(self.cas, digest=cache_id).descend('logs')
        return vdir

    # fetch_missing_blobs():
    #
    # Fetch missing blobs from configured remote repositories.
    #
    # Args:
    #     project (Project): The current project
    #     missing_blobs (list): The Digests of the blobs to fetch
    #
    def fetch_missing_blobs(self, project, missing_blobs):
        for remote in self._remotes[project]:
            if not missing_blobs:
                break

            remote.init()

            # fetch_blobs() will return the blobs that are still missing
            missing_blobs = self.cas.fetch_blobs(remote, missing_blobs)

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

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        remote_missing_blobs_set = set()

        for remote in push_remotes:
            remote.init()

            remote_missing_blobs = self.cas.remote_missing_blobs(remote, missing_blobs)
            remote_missing_blobs_set.update(remote_missing_blobs)

        return list(remote_missing_blobs_set)

    ################################################
    #             Local Private Methods            #
    ################################################

    # _reachable_directories()
    #
    # Returns:
    #     (iter): Iterator over directories digests available from artifacts.
    #
    def _reachable_directories(self):
        for root, _, files in os.walk(self.artifactdir):
            for artifact_file in files:
                artifact = artifact_pb2.Artifact()
                with open(os.path.join(root, artifact_file), 'r+b') as f:
                    artifact.ParseFromString(f.read())

                if str(artifact.files):
                    yield artifact.files

                if str(artifact.buildtree):
                    yield artifact.buildtree

    # _reachable_digests()
    #
    # Returns:
    #     (iter): Iterator over single file digests in artifacts
    #
    def _reachable_digests(self):
        for root, _, files in os.walk(self.artifactdir):
            for artifact_file in files:
                artifact = artifact_pb2.Artifact()
                with open(os.path.join(root, artifact_file), 'r+b') as f:
                    artifact.ParseFromString(f.read())

                if str(artifact.public_data):
                    yield artifact.public_data

                for log_file in artifact.logs:
                    yield log_file.digest

    # _push_artifact()
    #
    # Pushes relevant directories and then artifact proto to remote.
    #
    # Args:
    #    element (Element): element
    #    keys ([str]): keys to push
    #    artifact (Artifact): the artifact being pushed
    #    remote (CASRemote): remote to push to
    #
    # Returns:
    #    (bool): whether the push was successful
    #
    def _push_artifact(self, element, artifact, remote):

        artifact = artifact._get_proto()

        keys = [artifact.strong_key, artifact.weak_key]

        # Check whether the artifact is on the server
        present = False
        for key in keys:
            get_artifact = artifact_pb2.GetArtifactRequest()
            get_artifact.cache_key = element.get_artifact_name(key)
            try:
                artifact_service = artifact_pb2_grpc.ArtifactServiceStub(remote.channel)
                artifact_service.GetArtifact(get_artifact)
            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.NOT_FOUND:
                    raise ArtifactError("Error checking artifact cache: {}"
                                        .format(e.details()))
            else:
                present = True
        if present:
            return False

        try:
            self.cas._send_directory(remote, artifact.files)

            if str(artifact.buildtree):
                try:
                    self.cas._send_directory(remote, artifact.buildtree)
                except FileNotFoundError:
                    pass

            digests = []
            if str(artifact.public_data):
                digests.append(artifact.public_data)

            for log_file in artifact.logs:
                digests.append(log_file.digest)

            self.cas.send_blobs(remote, digests)

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise ArtifactError("Failed to push artifact blobs: {}".format(e.details()))
            return False

        # finally need to send the artifact proto
        for key in keys:
            update_artifact = artifact_pb2.UpdateArtifactRequest()
            update_artifact.cache_key = element.get_artifact_name(key)
            update_artifact.artifact.CopyFrom(artifact)

            try:
                artifact_service = artifact_pb2_grpc.ArtifactServiceStub(remote.channel)
                artifact_service.UpdateArtifact(update_artifact)
            except grpc.RpcError as e:
                raise ArtifactError("Failed to push artifact: {}".format(e.details()))

        return True

    # _pull_artifact()
    #
    # Args:
    #     element (Element): element to pull
    #     key (str): specific key of element to pull
    #     remote (CASRemote): remote to pull from
    #     pull_buildtree (bool): whether to pull buildtrees or not
    #
    # Returns:
    #     (bool): whether the pull was successful
    #
    def _pull_artifact(self, element, key, remote, pull_buildtrees=False):

        def __pull_digest(digest):
            self.cas._fetch_directory(remote, digest)
            required_blobs = self.cas.required_blobs_for_directory(digest)
            missing_blobs = self.cas.local_missing_blobs(required_blobs)
            if missing_blobs:
                self.cas.fetch_blobs(remote, missing_blobs)

        request = artifact_pb2.GetArtifactRequest()
        request.cache_key = element.get_artifact_name(key=key)
        try:
            artifact_service = artifact_pb2_grpc.ArtifactServiceStub(remote.channel)
            artifact = artifact_service.GetArtifact(request)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise ArtifactError("Failed to pull artifact: {}".format(e.details()))
            return False

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

        # Write the artifact proto to cache
        artifact_path = os.path.join(self.artifactdir, request.cache_key)
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        with open(artifact_path, 'w+b') as f:
            f.write(artifact.SerializeToString())

        return True
