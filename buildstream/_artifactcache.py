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

from ._basecache import BaseCache
from .types import _KeyStrength
from ._exceptions import ArtifactError, CASCacheError, CASError

from ._cas import CASRemoteSpec
from .storage._casbaseddirectory import CasBasedDirectory
from .storage.directory import VirtualDirectoryError


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

        self.casquota.add_ref_callbacks(self.required_artifacts)
        self.casquota.add_remove_callbacks((lambda x: not x.startswith('@'), self.remove))

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
                    try:
                        ref = element.get_artifact_name(key)

                        self.cas.update_mtime(ref)
                    except CASError:
                        pass

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

        return self.cas.contains(ref)

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
        return list(filter(
            lambda x: not x.startswith('@'),
            self.cas.list_refs(glob=glob)))

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
        return self.cas.remove(ref, defer_prune=defer_prune)

    # prune():
    #
    # Prune the artifact cache of unreachable refs
    #
    def prune(self):
        return self.cas.prune()

    # get_artifact_directory():
    #
    # Get virtual directory for cached artifact of the specified Element.
    #
    # Assumes artifact has previously been fetched or committed.
    #
    # Args:
    #     element (Element): The Element to extract
    #     key (str): The cache key to use
    #
    # Raises:
    #     ArtifactError: In cases there was an OSError, or if the artifact
    #                    did not exist.
    #
    # Returns: virtual directory object
    #
    def get_artifact_directory(self, element, key):
        ref = element.get_artifact_name(key)
        try:
            digest = self.cas.resolve_ref(ref, update_mtime=True)
            return CasBasedDirectory(self.cas, digest=digest)
        except (CASCacheError, VirtualDirectoryError) as e:
            raise ArtifactError('Directory not in local cache: {}'.format(e)) from e

    # commit():
    #
    # Commit built artifact to cache.
    #
    # Args:
    #     element (Element): The Element commit an artifact for
    #     content (Directory): The element's content directory
    #     keys (list): The cache keys to use
    #
    def commit(self, element, content, keys):
        refs = [element.get_artifact_name(key) for key in keys]

        tree = content._get_digest()

        for ref in refs:
            self.cas.set_ref(ref, tree)

    # diff():
    #
    # Return a list of files that have been added or modified between
    # the artifacts described by key_a and key_b.
    #
    # Args:
    #     element (Element): The element whose artifacts to compare
    #     key_a (str): The first artifact key
    #     key_b (str): The second artifact key
    #     subdir (str): A subdirectory to limit the comparison to
    #
    def diff(self, element, key_a, key_b, *, subdir=None):
        ref_a = element.get_artifact_name(key_a)
        ref_b = element.get_artifact_name(key_b)

        return self.cas.diff(ref_a, ref_b, subdir=subdir)

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
    def push(self, element, keys):
        refs = [element.get_artifact_name(key) for key in list(keys)]

        project = element._get_project()

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        pushed = False

        for remote in push_remotes:
            remote.init()
            display_key = element._get_brief_display_key()
            element.status("Pushing artifact {} -> {}".format(display_key, remote.spec.url))

            if self.cas.push(refs, remote):
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
    #     progress (callable): The progress callback, if any
    #     subdir (str): The optional specific subdir to pull
    #     excluded_subdirs (list): The optional list of subdirs to not pull
    #
    # Returns:
    #   (bool): True if pull was successful, False if artifact was not available
    #
    def pull(self, element, key, *, progress=None, subdir=None, excluded_subdirs=None):
        ref = element.get_artifact_name(key)
        display_key = key[:self.context.log_key_length]

        project = element._get_project()

        for remote in self._remotes[project]:
            try:
                element.status("Pulling artifact {} <- {}".format(display_key, remote.spec.url))

                if self.cas.pull(ref, remote, progress=progress, subdir=subdir, excluded_subdirs=excluded_subdirs):
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

        self.cas.link_ref(oldref, newref)

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
