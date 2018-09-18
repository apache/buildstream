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
import string
from collections import Mapping, namedtuple

from ..element import _KeyStrength
from .._exceptions import ArtifactError, ImplError, LoadError, LoadErrorReason
from .._message import Message, MessageType
from .. import utils
from .. import _yaml


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


# An ArtifactCache manages artifacts.
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache():
    def __init__(self, context):
        self.context = context
        self.extractdir = os.path.join(context.artifactdir, 'extract')
        self.tmpdir = os.path.join(context.artifactdir, 'tmp')

        self.global_remote_specs = []
        self.project_remote_specs = {}

        self._required_elements = set()       # The elements required for this session
        self._cache_size = None               # The current cache size, sometimes it's an estimate
        self._cache_quota = None              # The cache quota
        self._cache_lower_threshold = None    # The target cache size for a cleanup

        os.makedirs(self.extractdir, exist_ok=True)
        os.makedirs(self.tmpdir, exist_ok=True)

    ################################################
    #  Methods implemented on the abstract class   #
    ################################################

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
        # the atime of them.
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
                        self.update_atime(key)
                    except ArtifactError:
                        pass

    # clean():
    #
    # Clean the artifact cache as much as possible.
    #
    # Returns:
    #    (int): The size of the cache after having cleaned up
    #
    def clean(self):
        artifacts = self.list_artifacts()

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
            except IndexError:
                # If too many artifacts are required, and we therefore
                # can't remove them, we have to abort the build.
                #
                # FIXME: Asking the user what to do may be neater
                default_conf = os.path.join(os.environ['XDG_CONFIG_HOME'],
                                            'buildstream.conf')
                detail = ("There is not enough space to build the given element.\n"
                          "Please increase the cache-quota in {}."
                          .format(self.context.config_origin or default_conf))

                if self.get_quota_exceeded():
                    raise ArtifactError("Cache too full. Aborting.",
                                        detail=detail,
                                        reason="cache-too-full")
                else:
                    break

            key = to_remove.rpartition('/')[2]
            if key not in required_artifacts:

                # Remove the actual artifact, if it's not required.
                size = self.remove(to_remove)

                # Remove the size from the removed size
                self.set_cache_size(self._cache_size - size)

        # This should be O(1) if implemented correctly
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
        self._cache_size = self.calculate_cache_size()

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
    #     (int) An approximation of the artifact cache size.
    #
    def get_cache_size(self):

        # If we don't currently have an estimate, figure out the real cache size.
        if self._cache_size is None:
            stored_size = self._read_cache_size()
            if stored_size is not None:
                self._cache_size = stored_size
            else:
                self.compute_cache_size()

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

    # get_quota_exceeded()
    #
    # Checks if the current artifact cache size exceeds the quota.
    #
    # Returns:
    #    (bool): True of the quota is exceeded
    #
    def get_quota_exceeded(self):
        return self.get_cache_size() > self._cache_quota

    ################################################
    # Abstract methods for subclasses to implement #
    ################################################

    # update_atime()
    #
    # Update the atime of an artifact.
    #
    # Args:
    #     key (str): The key of the artifact.
    #
    def update_atime(self, key):
        raise ImplError("Cache '{kind}' does not implement contains()"
                        .format(kind=type(self).__name__))

    # initialize_remotes():
    #
    # This will contact each remote cache.
    #
    # Args:
    #     on_failure (callable): Called if we fail to contact one of the caches.
    #
    def initialize_remotes(self, *, on_failure=None):
        pass

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
        raise ImplError("Cache '{kind}' does not implement contains()"
                        .format(kind=type(self).__name__))

    # list_artifacts():
    #
    # List artifacts in this cache in LRU order.
    #
    # Returns:
    #     ([str]) - A list of artifact names as generated by
    #               `ArtifactCache.get_artifact_fullname` in LRU order
    #
    def list_artifacts(self):
        raise ImplError("Cache '{kind}' does not implement list_artifacts()"
                        .format(kind=type(self).__name__))

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
    def remove(self, artifact_name):
        raise ImplError("Cache '{kind}' does not implement remove()"
                        .format(kind=type(self).__name__))

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
        raise ImplError("Cache '{kind}' does not implement extract()"
                        .format(kind=type(self).__name__))

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
        raise ImplError("Cache '{kind}' does not implement commit()"
                        .format(kind=type(self).__name__))

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
        raise ImplError("Cache '{kind}' does not implement diff()"
                        .format(kind=type(self).__name__))

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
        return False

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
        return False

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
        raise ImplError("Cache '{kind}' does not implement push()"
                        .format(kind=type(self).__name__))

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
        raise ImplError("Cache '{kind}' does not implement pull()"
                        .format(kind=type(self).__name__))

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
        raise ImplError("Cache '{kind}' does not implement link_key()"
                        .format(kind=type(self).__name__))

    # calculate_cache_size()
    #
    # Return the real artifact cache size.
    #
    # Returns:
    #    (int): The size of the artifact cache.
    #
    def calculate_cache_size(self):
        raise ImplError("Cache '{kind}' does not implement calculate_cache_size()"
                        .format(kind=type(self).__name__))

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

        if not os.path.exists(size_file_path):
            return None

        with open(size_file_path, "r") as f:
            size = f.read()

        try:
            num_size = int(size)
        except ValueError as e:
            raise ArtifactError("Size '{}' parsed from '{}' was not an integer".format(
                size, size_file_path)) from e

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

        artifactdir_volume = self.context.artifactdir
        while not os.path.exists(artifactdir_volume):
            artifactdir_volume = os.path.dirname(artifactdir_volume)

        try:
            cache_quota = utils._parse_size(self.context.config_cache_quota, artifactdir_volume)
        except utils.UtilError as e:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}\nPlease specify the value in bytes or as a % of full disk space.\n"
                            "\nValid values are, for example: 800M 10G 1T 50%\n"
                            .format(str(e))) from e

        stat = os.statvfs(artifactdir_volume)
        available_space = (stat.f_bsize * stat.f_bavail)

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
        elif cache_quota > cache_size + available_space:  # Check maximum
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            ("Your system does not have enough available " +
                             "space to support the cache quota specified.\n" +
                             "You currently have:\n" +
                             "- {used} of cache in use at {local_cache_path}\n" +
                             "- {available} of available system storage").format(
                                 used=utils._pretty_size(cache_size),
                                 local_cache_path=self.context.artifactdir,
                                 available=utils._pretty_size(available_space)))

        # Place a slight headroom (2e9 (2GB) on the cache_quota) into
        # cache_quota to try and avoid exceptions.
        #
        # Of course, we might still end up running out during a build
        # if we end up writing more than 2G, but hey, this stuff is
        # already really fuzzy.
        #
        self._cache_quota = cache_quota - headroom
        self._cache_lower_threshold = self._cache_quota / 2


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
