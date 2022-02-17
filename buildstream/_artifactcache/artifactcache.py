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

import multiprocessing
import os
import signal
import string
from collections import namedtuple
from collections.abc import Mapping

from ..types import _KeyStrength
from .._exceptions import ArtifactError, CASError, LoadError, LoadErrorReason
from .._message import Message, MessageType
from .. import _signals
from .. import utils
from .. import _yaml

from .cascache import CASCache, CASRemote, BlobNotFound


CACHE_SIZE_FILE = "cache_size"


# An ArtifactCacheSpec holds the user configuration for a single remote
# artifact cache.
#
# Args:
#     url (str): Location of the remote artifact cache
#     push (bool): Whether we should attempt to push artifacts to this cache,
#                  in addition to pulling from it.
#
class ArtifactCacheSpec(namedtuple('ArtifactCacheSpec', 'url push server_cert client_key client_cert')):

    # _new_from_config_node
    #
    # Creates an ArtifactCacheSpec() from a YAML loaded node
    #
    @staticmethod
    def _new_from_config_node(spec_node, basedir=None):
        _yaml.node_validate(spec_node, ['url', 'push', 'server-cert', 'client-key', 'client-cert'])
        url = _yaml.node_get(spec_node, str, 'url')
        push = _yaml.node_get(spec_node, bool, 'push', default_value=False)
        if not url:
            provenance = _yaml.node_get_provenance(spec_node, 'url')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: empty artifact cache URL".format(provenance))

        server_cert = _yaml.node_get(spec_node, str, 'server-cert', default_value=None)
        if server_cert and basedir:
            server_cert = os.path.join(basedir, server_cert)

        client_key = _yaml.node_get(spec_node, str, 'client-key', default_value=None)
        if client_key and basedir:
            client_key = os.path.join(basedir, client_key)

        client_cert = _yaml.node_get(spec_node, str, 'client-cert', default_value=None)
        if client_cert and basedir:
            client_cert = os.path.join(basedir, client_cert)

        if client_key and not client_cert:
            provenance = _yaml.node_get_provenance(spec_node, 'client-key')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: 'client-key' was specified without 'client-cert'".format(provenance))

        if client_cert and not client_key:
            provenance = _yaml.node_get_provenance(spec_node, 'client-cert')
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: 'client-cert' was specified without 'client-key'".format(provenance))

        return ArtifactCacheSpec(url, push, server_cert, client_key, client_cert)


ArtifactCacheSpec.__new__.__defaults__ = (None, None, None)


# ArtifactCacheUsage
#
# A simple object to report the current artifact cache
# usage details.
#
# Note that this uses the user configured cache quota
# rather than the internal quota with protective headroom
# removed, to provide a more sensible value to display to
# the user.
#
# Args:
#    artifacts (ArtifactCache): The artifact cache to get the status of
#
class ArtifactCacheUsage():

    def __init__(self, artifacts):
        context = artifacts.context
        self.quota_config = context.config_cache_quota       # Configured quota
        self.quota_size = artifacts._cache_quota_original    # Resolved cache quota in bytes
        self.used_size = artifacts.get_cache_size()          # Size used by artifacts in bytes
        self.used_percent = 0                                # Percentage of the quota used
        if self.quota_size is not None:
            self.used_percent = int(self.used_size * 100 / self.quota_size)

    # Formattable into a human readable string
    #
    def __str__(self):
        return "{} / {} ({}%)" \
            .format(utils._pretty_size(self.used_size, dec_places=1),
                    self.quota_config,
                    self.used_percent)


# An ArtifactCache manages artifacts.
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache():
    def __init__(self, context):
        self.context = context
        self.extractdir = os.path.join(context.artifactdir, 'extract')

        self.cas = CASCache(context.artifactdir)

        self.global_remote_specs = []
        self.project_remote_specs = {}

        self._required_elements = set()       # The elements required for this session
        self._cache_size = None               # The current cache size, sometimes it's an estimate
        self._cache_quota = None              # The cache quota
        self._cache_quota_original = None     # The cache quota as specified by the user, in bytes
        self._cache_lower_threshold = None    # The target cache size for a cleanup

        # Per-project list of _CASRemote instances.
        self._remotes = {}

        self._has_fetch_remotes = False
        self._has_push_remotes = False

        os.makedirs(self.extractdir, exist_ok=True)

        self._calculate_cache_quota()

    # get_artifact_fullname()
    #
    # Generate a full name for an artifact, including the
    # project namespace, element name and cache key.
    #
    # This can also be used as a relative path safely, and
    # will normalize parts of the element name such that only
    # digits, letters and some select characters are allowed.
    #
    # Args:
    #    element (Element): The Element object
    #    key (str): The element's cache key
    #
    # Returns:
    #    (str): The relative path for the artifact
    #
    def get_artifact_fullname(self, element, key):
        project = element._get_project()

        # Normalize ostree ref unsupported chars
        valid_chars = string.digits + string.ascii_letters + '-._'
        element_name = ''.join([
            x if x in valid_chars else '_'
            for x in element.normal_name
        ])

        assert key is not None

        # assume project and element names are not allowed to contain slashes
        return '{0}/{1}/{2}'.format(project.name, element_name, key)

    # setup_remotes():
    #
    # Sets up which remotes to use
    #
    # Args:
    #    use_config (bool): Whether to use project configuration
    #    remote_url (str): Remote artifact cache URL
    #
    # This requires that all of the projects which are to be processed in the session
    # have already been loaded and are observable in the Context.
    #
    def setup_remotes(self, *, use_config=False, remote_url=None):

        # Initialize remote artifact caches. We allow the commandline to override
        # the user config in some cases (for example `bst push --remote=...`).
        has_remote_caches = False
        if remote_url:
            self._set_remotes([ArtifactCacheSpec(remote_url, push=True)])
            has_remote_caches = True
        if use_config:
            for project in self.context.get_projects():
                artifact_caches = _configured_remote_artifact_cache_specs(self.context, project)
                if artifact_caches:  # artifact_caches is a list of ArtifactCacheSpec instances
                    self._set_remotes(artifact_caches, project=project)
                    has_remote_caches = True
        if has_remote_caches:
            self._initialize_remotes()

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
    @staticmethod
    def specs_from_config_node(config_node, basedir=None):
        cache_specs = []

        artifacts = config_node.get('artifacts', [])
        if isinstance(artifacts, Mapping):
            cache_specs.append(ArtifactCacheSpec._new_from_config_node(artifacts, basedir))
        elif isinstance(artifacts, list):
            for spec_node in artifacts:
                cache_specs.append(ArtifactCacheSpec._new_from_config_node(spec_node, basedir))
        else:
            provenance = _yaml.node_get_provenance(config_node, key='artifacts')
            raise _yaml.LoadError(_yaml.LoadErrorReason.INVALID_DATA,
                                  "%s: 'artifacts' must be a single 'url:' mapping, or a list of mappings" %
                                  (str(provenance)))
        return cache_specs

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
                        ref = self.get_artifact_fullname(element, key)

                        self.cas.update_mtime(ref)
                    except CASError:
                        pass

    # clean():
    #
    # Clean the artifact cache as much as possible.
    #
    # Args:
    #    progress (callable): A callback to call when a ref is removed
    #
    # Returns:
    #    (int): The size of the cache after having cleaned up
    #
    def clean(self, progress=None):
        artifacts = self.list_artifacts()
        context = self.context

        # Some accumulative statistics
        removed_ref_count = 0
        space_saved = 0

        # Start off with an announcement with as much info as possible
        volume_size, volume_avail = self._get_cache_volume_size()
        self._message(MessageType.STATUS, "Starting cache cleanup",
                      detail=("Elements required by the current build plan: {}\n" +
                              "User specified quota: {} ({})\n" +
                              "Cache usage: {}\n" +
                              "Cache volume: {} total, {} available")
                      .format(len(self._required_elements),
                              context.config_cache_quota,
                              utils._pretty_size(self._cache_quota_original, dec_places=2),
                              utils._pretty_size(self.get_cache_size(), dec_places=2),
                              utils._pretty_size(volume_size, dec_places=2),
                              utils._pretty_size(volume_avail, dec_places=2)))

        # Build a set of the cache keys which are required
        # based on the required elements at cleanup time
        #
        # We lock both strong and weak keys - deleting one but not the
        # other won't save space, but would be a user inconvenience.
        required_artifacts = set()
        for element in self._required_elements:
            required_artifacts.update([
                element._get_cache_key(strength=_KeyStrength.STRONG),
                element._get_cache_key(strength=_KeyStrength.WEAK)
            ])

        # Do a real computation of the cache size once, just in case
        self.compute_cache_size()

        while self.get_cache_size() >= self._cache_lower_threshold:
            try:
                to_remove = artifacts.pop(0)
            except IndexError as e:
                # If too many artifacts are required, and we therefore
                # can't remove them, we have to abort the build.
                #
                # FIXME: Asking the user what to do may be neater
                #
                default_conf = os.path.join(os.environ['XDG_CONFIG_HOME'],
                                            'buildstream.conf')
                detail = ("Aborted after removing {} refs and saving {} disk space.\n"
                          "The remaining {} in the cache is required by the {} elements in your build plan\n\n"
                          "There is not enough space to complete the build.\n"
                          "Please increase the cache-quota in {} and/or make more disk space."
                          .format(removed_ref_count,
                                  utils._pretty_size(space_saved, dec_places=2),
                                  utils._pretty_size(self.get_cache_size(), dec_places=2),
                                  len(self._required_elements),
                                  (context.config_origin or default_conf)))

                if self.has_quota_exceeded():
                    raise ArtifactError("Cache too full. Aborting.",
                                        detail=detail,
                                        reason="cache-too-full") from e
                break

            key = to_remove.rpartition('/')[2]
            if key not in required_artifacts:

                # Remove the actual artifact, if it's not required.
                size = self.remove(to_remove)

                removed_ref_count += 1
                space_saved += size

                self._message(MessageType.STATUS,
                              "Freed {: <7} {}".format(
                                  utils._pretty_size(size, dec_places=2),
                                  to_remove))

                # Remove the size from the removed size
                self.set_cache_size(self._cache_size - size)

                # User callback
                #
                # Currently this process is fairly slow, but we should
                # think about throttling this progress() callback if this
                # becomes too intense.
                if progress:
                    progress()

        # Informational message about the side effects of the cleanup
        self._message(MessageType.INFO, "Cleanup completed",
                      detail=("Removed {} refs and saving {} disk space.\n" +
                              "Cache usage is now: {}")
                      .format(removed_ref_count,
                              utils._pretty_size(space_saved, dec_places=2),
                              utils._pretty_size(self.get_cache_size(), dec_places=2)))

        return self.get_cache_size()

    # compute_cache_size()
    #
    # Computes the real artifact cache size by calling
    # the abstract calculate_cache_size() method.
    #
    # Returns:
    #    (int): The size of the artifact cache.
    #
    def compute_cache_size(self):
        old_cache_size = self._cache_size
        new_cache_size = self.cas.calculate_cache_size()

        if old_cache_size != new_cache_size:
            self._cache_size = new_cache_size

            usage = ArtifactCacheUsage(self)
            self._message(MessageType.STATUS, "Cache usage recomputed: {}".format(usage))

        return self._cache_size

    # add_artifact_size()
    #
    # Adds the reported size of a newly cached artifact to the
    # overall estimated size.
    #
    # Args:
    #     artifact_size (int): The size to add.
    #
    def add_artifact_size(self, artifact_size):
        cache_size = self.get_cache_size()
        cache_size += artifact_size

        self.set_cache_size(cache_size)

    # get_cache_size()
    #
    # Fetches the cached size of the cache, this is sometimes
    # an estimate and periodically adjusted to the real size
    # when a cache size calculation job runs.
    #
    # When it is an estimate, the value is either correct, or
    # it is greater than the actual cache size.
    #
    # Returns:
    #     (int) An approximation of the artifact cache size, in bytes.
    #
    def get_cache_size(self):

        # If we don't currently have an estimate, figure out the real cache size.
        if self._cache_size is None:
            stored_size = self._read_cache_size()
            if stored_size is not None:
                self._cache_size = stored_size
            else:
                self.compute_cache_size()
                # Computing cache doesn't actually write the value.
                # Write cache size explicitly here since otherwise
                # in some cases it's not stored on disk.
                self.set_cache_size(self._cache_size)

        return self._cache_size

    # set_cache_size()
    #
    # Forcefully set the overall cache size.
    #
    # This is used to update the size in the main process after
    # having calculated in a cleanup or a cache size calculation job.
    #
    # Args:
    #     cache_size (int): The size to set.
    #
    def set_cache_size(self, cache_size):

        assert cache_size is not None

        self._cache_size = cache_size
        self._write_cache_size(self._cache_size)

    # has_quota_exceeded()
    #
    # Checks if the current artifact cache size exceeds the quota.
    #
    # Returns:
    #    (bool): True of the quota is exceeded
    #
    def has_quota_exceeded(self):
        return self.get_cache_size() > self._cache_quota

    # preflight():
    #
    # Preflight check.
    #
    def preflight(self):
        self.cas.preflight()

    # initialize_remotes():
    #
    # This will contact each remote cache.
    #
    # Args:
    #     on_failure (callable): Called if we fail to contact one of the caches.
    #
    def initialize_remotes(self, *, on_failure=None):
        remote_specs = self.global_remote_specs

        for _, project_specs in self.project_remote_specs.items():
            remote_specs += project_specs

        remote_specs = list(utils._deduplicate(remote_specs))

        remotes = {}
        q = multiprocessing.Queue()
        for remote_spec in remote_specs:
            # Use subprocess to avoid creation of gRPC threads in main BuildStream process
            # See https://github.com/grpc/grpc/blob/master/doc/fork_support.md for details
            p = multiprocessing.Process(target=self.cas.initialize_remote, args=(remote_spec, q))

            try:
                # Keep SIGINT blocked in the child process
                with _signals.blocked([signal.SIGINT], ignore=False):
                    p.start()

                error = q.get()
                p.join()
            except KeyboardInterrupt:
                utils._kill_process_tree(p.pid)
                raise

            if error and on_failure:
                on_failure(remote_spec.url, error)
            elif error:
                raise ArtifactError(error)
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
        ref = self.get_artifact_fullname(element, key)

        return self.cas.contains(ref)

    # list_artifacts():
    #
    # List artifacts in this cache in LRU order.
    #
    # Returns:
    #     ([str]) - A list of artifact names as generated by
    #               `ArtifactCache.get_artifact_fullname` in LRU order
    #
    def list_artifacts(self):
        return self.cas.list_refs()

    # remove():
    #
    # Removes the artifact for the specified ref from the local
    # artifact cache.
    #
    # Args:
    #     ref (artifact_name): The name of the artifact to remove (as
    #                          generated by
    #                          `ArtifactCache.get_artifact_fullname`)
    #
    # Returns:
    #    (int|None) The amount of space pruned from the repository in
    #               Bytes, or None if defer_prune is True
    #
    def remove(self, ref):

        # Remove extract if not used by other ref
        tree = self.cas.resolve_ref(ref)
        ref_name, ref_hash = os.path.split(ref)
        extract = os.path.join(self.extractdir, ref_name, tree.hash)
        keys_file = os.path.join(extract, 'meta', 'keys.yaml')
        if os.path.exists(keys_file):
            keys_meta = _yaml.load(keys_file)
            keys = [keys_meta['strong'], keys_meta['weak']]
            remove_extract = True
            for other_hash in keys:
                if other_hash == ref_hash:
                    continue
                remove_extract = False
                break

            if remove_extract:
                utils._force_rmtree(extract)

        return self.cas.remove(ref)

    # extract():
    #
    # Extract cached artifact for the specified Element if it hasn't
    # already been extracted.
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
    # Returns: path to extracted artifact
    #
    def extract(self, element, key):
        ref = self.get_artifact_fullname(element, key)

        path = os.path.join(self.extractdir, element._get_project().name, element.normal_name)

        return self.cas.extract(ref, path)

    # commit():
    #
    # Commit built artifact to cache.
    #
    # Args:
    #     element (Element): The Element commit an artifact for
    #     content (str): The element's content directory
    #     keys (list): The cache keys to use
    #
    def commit(self, element, content, keys):
        refs = [self.get_artifact_fullname(element, key) for key in keys]

        self.cas.commit(refs, content)

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
        ref_a = self.get_artifact_fullname(element, key_a)
        ref_b = self.get_artifact_fullname(element, key_b)

        return self.cas.diff(ref_a, ref_b, subdir=subdir)

    # has_fetch_remotes():
    #
    # Check whether any remote repositories are available for fetching.
    #
    # Args:
    #     element (Element): The Element to check
    #
    # Returns: True if any remote repositories are configured, False otherwise
    #
    def has_fetch_remotes(self, *, element=None):
        if not self._has_fetch_remotes:
            # No project has fetch remotes
            return False
        elif element is None:
            # At least one (sub)project has fetch remotes
            return True
        else:
            # Check whether the specified element's project has fetch remotes
            remotes_for_project = self._remotes[element._get_project()]
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
    def has_push_remotes(self, *, element=None):
        if not self._has_push_remotes:
            # No project has push remotes
            return False
        elif element is None:
            # At least one (sub)project has push remotes
            return True
        else:
            # Check whether the specified element's project has push remotes
            remotes_for_project = self._remotes[element._get_project()]
            return any(remote.spec.push for remote in remotes_for_project)

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
        refs = [self.get_artifact_fullname(element, key) for key in list(keys)]

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
                element.info("Remote ({}) already has {} cached".format(
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
    #
    # Returns:
    #   (bool): True if pull was successful, False if artifact was not available
    #
    def pull(self, element, key, *, progress=None):
        ref = self.get_artifact_fullname(element, key)
        display_key = key[:self.context.log_key_length]

        project = element._get_project()

        for remote in self._remotes[project]:
            try:
                element.status("Pulling artifact {} <- {}".format(display_key, remote.spec.url))

                if self.cas.pull(ref, remote, progress=progress):
                    element.info("Pulled artifact {} <- {}".format(display_key, remote.spec.url))
                    # no need to pull from additional remotes
                    return True
                else:
                    element.info("Remote ({}) does not have {} cached".format(
                        remote.spec.url, display_key
                    ))
            except BlobNotFound:
                element.info("Remote ({}) does not have {} cached".format(
                    remote.spec.url, display_key
                ))
            except CASError as e:
                raise ArtifactError("Failed to pull artifact {}: {}".format(
                    display_key, e)) from e

        return False

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
        oldref = self.get_artifact_fullname(element, oldkey)
        newref = self.get_artifact_fullname(element, newkey)

        self.cas.link_ref(oldref, newref)

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

    # _write_cache_size()
    #
    # Writes the given size of the artifact to the cache's size file
    #
    # Args:
    #    size (int): The size of the artifact cache to record
    #
    def _write_cache_size(self, size):
        assert isinstance(size, int)
        size_file_path = os.path.join(self.context.artifactdir, CACHE_SIZE_FILE)
        with utils.save_file_atomic(size_file_path, "w") as f:
            f.write(str(size))

    # _read_cache_size()
    #
    # Reads and returns the size of the artifact cache that's stored in the
    # cache's size file
    #
    # Returns:
    #    (int): The size of the artifact cache, as recorded in the file
    #
    def _read_cache_size(self):
        size_file_path = os.path.join(self.context.artifactdir, CACHE_SIZE_FILE)

        try:
            with open(size_file_path, "r", encoding="utf-8") as f:
                size = f.read()
        except FileNotFoundError:
            return None

        try:
            num_size = int(size)
        except ValueError:
            self._message(MessageType.WARN, "Failure resolving cache size",
                          detail="Size '{}' parsed from '{}' was not an integer"
                          .format(size, size_file_path))
            return None
        else:
            return num_size

    # _calculate_cache_quota()
    #
    # Calculates and sets the cache quota and lower threshold based on the
    # quota set in Context.
    # It checks that the quota is both a valid expression, and that there is
    # enough disk space to satisfy that quota
    #
    def _calculate_cache_quota(self):
        # Headroom intended to give BuildStream a bit of leeway.
        # This acts as the minimum size of cache_quota and also
        # is taken from the user requested cache_quota.
        #
        if 'BST_TEST_SUITE' in os.environ:
            headroom = 0
        else:
            headroom = 2e9

        try:
            cache_quota = utils._parse_size(self.context.config_cache_quota,
                                            self.context.artifactdir)
        except utils.UtilError as e:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}\nPlease specify the value in bytes or as a % of full disk space.\n"
                            "\nValid values are, for example: 800M 10G 1T 50%\n"
                            .format(str(e))) from e

        total_size, available_space = self._get_cache_volume_size()
        cache_size = self.get_cache_size()

        # Ensure system has enough storage for the cache_quota
        #
        # If cache_quota is none, set it to the maximum it could possibly be.
        #
        # Also check that cache_quota is at least as large as our headroom.
        #
        if cache_quota is None:  # Infinity, set to max system storage
            cache_quota = cache_size + available_space
        if cache_quota < headroom:  # Check minimum
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "Invalid cache quota ({}): ".format(utils._pretty_size(cache_quota)) +
                            "BuildStream requires a minimum cache quota of 2G.")
        if cache_quota > cache_size + available_space:  # Check maximum
            if '%' in self.context.config_cache_quota:
                available = (available_space / total_size) * 100
                available = '{}% of total disk space'.format(round(available, 1))
            else:
                available = utils._pretty_size(available_space)

            raise ArtifactError("Your system does not have enough available " +
                                "space to support the cache quota specified.",
                                detail=("You have specified a quota of {quota} total disk space.\n" +
                                        "The filesystem containing {local_cache_path} only " +
                                        "has {available_size} available.")
                                .format(
                                    quota=self.context.config_cache_quota,
                                    local_cache_path=self.context.artifactdir,
                                    available_size=available),
                                reason='insufficient-storage-for-quota')

        # Place a slight headroom (2e9 (2GB) on the cache_quota) into
        # cache_quota to try and avoid exceptions.
        #
        # Of course, we might still end up running out during a build
        # if we end up writing more than 2G, but hey, this stuff is
        # already really fuzzy.
        #
        self._cache_quota_original = cache_quota
        self._cache_quota = cache_quota - headroom
        self._cache_lower_threshold = self._cache_quota / 2

    # _get_cache_volume_size()
    #
    # Get the available space and total space for the volume on
    # which the artifact cache is located.
    #
    # Returns:
    #    (int): The total number of bytes on the volume
    #    (int): The number of available bytes on the volume
    #
    # NOTE: We use this stub to allow the test cases
    #       to override what an artifact cache thinks
    #       about it's disk size and available bytes.
    #
    def _get_cache_volume_size(self):
        return utils._get_volume_size(self.context.artifactdir)


# _configured_remote_artifact_cache_specs():
#
# Return the list of configured artifact remotes for a given project, in priority
# order. This takes into account the user and project configuration.
#
# Args:
#     context (Context): The BuildStream context
#     project (Project): The BuildStream project
#
# Returns:
#   A list of ArtifactCacheSpec instances describing the remote artifact caches.
#
def _configured_remote_artifact_cache_specs(context, project):
    project_overrides = context.get_overrides(project.name)
    project_extra_specs = ArtifactCache.specs_from_config_node(project_overrides)

    return list(utils._deduplicate(
        project_extra_specs + project.artifact_cache_specs + context.artifact_cache_specs))
