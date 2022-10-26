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
#        Tom Pollard <tom.pollard@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

"""
Artifact
=========

Implementation of the Artifact class which aims to 'abstract' direct
artifact composite interaction away from Element class

"""

import os
import tempfile
from typing import Dict, Tuple

from ._protos.buildstream.v2.artifact_pb2 import Artifact as ArtifactProto
from . import _yaml
from . import utils
from .node import Node
from .types import _Scope
from .storage._casbaseddirectory import CasBasedDirectory
from .sandbox._config import SandboxConfig
from ._variables import Variables

# An Artifact class to abstract artifact operations
# from the Element class
#
# Args:
#     element (Element): The Element object
#     context (Context): The BuildStream context
#     strong_key (str): The elements strong cache key, dependent on context
#     strict_key (str): The elements strict cache key
#     weak_key (str): The elements weak cache key
#
class Artifact:

    version = 2

    def __init__(self, element, context, *, strong_key=None, strict_key=None, weak_key=None):
        self._element = element
        self._context = context
        self._cache_key = strong_key
        self._strict_key = strict_key
        self._weak_cache_key = weak_key
        self._artifactdir = context.artifactdir
        self._cas = context.get_cascache()
        self._tmpdir = context.tmpdir
        self._proto = None

        self._metadata_keys = None  # Strong, strict and weak key tuple extracted from the artifact
        self._metadata_dependencies = None  # Dictionary of dependency strong keys from the artifact
        self._metadata_workspaced = None  # Boolean of whether it's a workspaced artifact
        self._metadata_workspaced_dependencies = None  # List of which dependencies are workspaced from the artifact
        self._cached = None  # Boolean of whether the artifact is cached

    # strong_key():
    #
    # A property which evaluates to the strong key, regardless of whether
    # it was the strong key that the Artifact object was initialized with
    # or whether it was the strong key loaded from artifact metadata.
    #
    @property
    def strong_key(self) -> str:
        if self.cached():
            key, _, _ = self.get_metadata_keys()
        else:
            key = self._cache_key

        return key

    # strict_key():
    #
    # A property which evaluates to the strict key, regardless of whether
    # it was the strict key that the Artifact object was initialized with
    # or whether it was the strict key loaded from artifact metadata.
    #
    @property
    def strict_key(self) -> str:
        if self.cached():
            _, key, _ = self.get_metadata_keys()
        else:
            key = self._strict_key

        return key

    # weak_key():
    #
    # A property which evaluates to the weak key, regardless of whether
    # it was the weak key that the Artifact object was initialized with
    # or whether it was the weak key loaded from artifact metadata.
    #
    @property
    def weak_key(self) -> str:
        if self.cached():
            _, _, key = self.get_metadata_keys()
        else:
            key = self._weak_cache_key

        return key

    # get_files():
    #
    # Get a virtual directory for the artifact files content
    #
    # Returns:
    #    (Directory): The virtual directory object
    #
    def get_files(self):
        files_digest = self._get_field_digest("files")
        return CasBasedDirectory(self._cas, digest=files_digest)

    # get_buildroot():
    #
    # Get a virtual directory for the artifact buildroot content
    #
    # Returns:
    #    (Directory): The virtual directory object
    #
    def get_buildroot(self):
        buildroot_digest = self._get_field_digest("buildroot")

        return CasBasedDirectory(self._cas, digest=buildroot_digest)

    # get_buildtree():
    #
    # Get a virtual directory for the artifact buildtree content
    #
    # Returns:
    #    (Directory): The virtual directory object
    #
    def get_buildtree(self):
        buildtree_digest = self._get_field_digest("buildtree")

        return CasBasedDirectory(self._cas, digest=buildtree_digest)

    # get_sources():
    #
    # Get a virtual directory for the artifact sources
    #
    # Returns:
    #    (Directory): The virtual directory object
    #
    def get_sources(self):
        sources_digest = self._get_field_digest("sources")

        return CasBasedDirectory(self._cas, digest=sources_digest)

    # get_logs():
    #
    # Get the paths of the artifact's logs
    #
    # Returns:
    #    (list): A list of object paths
    #
    def get_logs(self):
        artifact = self._get_proto()

        logfile_paths = []
        for logfile in artifact.logs:
            logfile_paths.append(self._cas.objpath(logfile.digest))

        return logfile_paths

    # get_extract_key():
    #
    # Get the key used to extract the artifact
    #
    # Returns:
    #    (str): The key
    #
    def get_extract_key(self):
        return self._cache_key or self._weak_cache_key

    # cache():
    #
    # Create the artifact and commit to cache
    #
    # Args:
    #    buildrootvdir (Directory): The root directory of the build sandbox
    #    sandbox_build_dir (Directory): Virtual Directory object for the sandbox build-root
    #    collectvdir (Directory): Virtual Directoy object from within the sandbox for collection
    #    sourcesvdir (Directory): Virtual Directoy object for the staged sources
    #    buildresult (tuple): bool, short desc and detailed desc of result
    #    publicdata (dict): dict of public data to commit to artifact metadata
    #    variables (Variables): The element's Variables
    #    environment (dict): dict of the element's environment variables
    #    sandboxconfig (SandboxConfig): The element's SandboxConfig
    #
    def cache(
        self,
        *,
        buildrootvdir,
        sandbox_build_dir,
        collectvdir,
        sourcesvdir,
        buildresult,
        publicdata,
        variables,
        environment,
        sandboxconfig,
    ):

        context = self._context
        element = self._element
        size = 0

        filesvdir = None
        buildtreevdir = None

        artifact = ArtifactProto()

        artifact.version = self.version

        # Store result
        artifact.build_success = buildresult[0]
        artifact.build_error = buildresult[1]
        artifact.build_error_details = "" if not buildresult[2] else buildresult[2]

        # Store keys
        artifact.strong_key = self._cache_key
        artifact.strict_key = self._strict_key
        artifact.weak_key = self._weak_cache_key

        artifact.was_workspaced = bool(element._get_workspace())
        properties = ["mtime"] if artifact.was_workspaced else []

        # Store files
        if collectvdir is not None:
            filesvdir = CasBasedDirectory(cas_cache=self._cas)
            filesvdir._import_files_internal(collectvdir, properties=properties, collect_result=False)
            artifact.files.CopyFrom(filesvdir._get_digest())
            size += filesvdir._get_size()

        with tempfile.TemporaryDirectory() as tmpdir:
            files_to_capture = []

            # Store public data
            tmpname = os.path.join(tmpdir, "public_data")
            _yaml.roundtrip_dump(publicdata, tmpname)
            files_to_capture.append((tmpname, artifact.public_data))

            # Store low diversity metadata, this metadata must have a high
            # probability of deduplication, such as environment variables
            # and SandboxConfig.
            #
            sandbox_dict = sandboxconfig.to_dict()
            low_diversity_dict = {"environment": environment, "sandbox-config": sandbox_dict}
            low_diversity_node = Node.from_dict(low_diversity_dict)

            tmpname = os.path.join(tmpdir, "low_diversity_meta")
            _yaml.roundtrip_dump(low_diversity_node, tmpname)
            files_to_capture.append((tmpname, artifact.low_diversity_meta))

            # Store high diversity metadata, this metadata is expected to diverge
            # for every element and as such cannot be deduplicated.
            #
            # The Variables object supports being converted directly to a dictionary
            variables_dict = dict(variables)
            high_diversity_dict = {"variables": variables_dict}
            high_diversity_node = Node.from_dict(high_diversity_dict)

            tmpname = os.path.join(tmpdir, "high_diversity_meta")
            _yaml.roundtrip_dump(high_diversity_node, tmpname)
            files_to_capture.append((tmpname, artifact.high_diversity_meta))

            # Store log file
            log_filename = context.messenger.get_log_filename()
            if log_filename:
                log = artifact.logs.add()
                log.name = os.path.basename(log_filename)
                files_to_capture.append((log_filename, log.digest))

            # Capture queued files and store returned digests
            digests = self._cas.add_objects(paths=[entry[0] for entry in files_to_capture])
            # add_objects() should guarantee this.
            # `zip(..., strict=True)` could be used in Python 3.10+
            assert len(files_to_capture) == len(digests)
            for entry, digest in zip(files_to_capture, digests):
                entry[1].CopyFrom(digest)

        # store build dependencies
        for e in element._dependencies(_Scope.BUILD):
            new_build = artifact.build_deps.add()
            new_build.project_name = e.project_name
            new_build.element_name = e.name
            new_build.cache_key = e._get_cache_key()
            new_build.was_workspaced = bool(e._get_workspace())

        # Store build tree
        if sandbox_build_dir is not None:
            buildtreevdir = CasBasedDirectory(cas_cache=self._cas)
            buildtreevdir._import_files_internal(sandbox_build_dir, properties=properties, collect_result=False)
            artifact.buildtree.CopyFrom(buildtreevdir._get_digest())

        # Store sources
        if sourcesvdir is not None:
            artifact.sources.CopyFrom(sourcesvdir._get_digest())

        # Store build root
        if buildrootvdir is not None:
            rootvdir = CasBasedDirectory(cas_cache=self._cas)
            rootvdir._import_files_internal(buildrootvdir, properties=properties, collect_result=False)
            artifact.buildroot.CopyFrom(rootvdir._get_digest())

        os.makedirs(os.path.dirname(os.path.join(self._artifactdir, element.get_artifact_name())), exist_ok=True)
        keys = utils._deduplicate([self._cache_key, self._weak_cache_key])
        for key in keys:
            path = os.path.join(self._artifactdir, element.get_artifact_name(key=key))
            with utils.save_file_atomic(path, mode="wb") as f:
                f.write(artifact.SerializeToString())

    # cached_buildroot()
    #
    # Check if artifact is cached with expected buildroot. A
    # buildroot will not be present if the rest of the partial artifact
    # is not cached.
    #
    # Returns:
    #     (bool): True if artifact cached with buildroot, False if
    #             missing expected buildroot. Note this only confirms
    #             if a buildroot is present, not its contents.
    #
    def cached_buildroot(self):

        buildroot_digest = self._get_field_digest("buildroot")
        if buildroot_digest:
            return self._cas.contains_directory(buildroot_digest, with_files=True)
        else:
            return False

    # buildroot_exists()
    #
    # Check if artifact was created with a buildroot. This does not check
    # whether the buildroot is present in the local cache.
    #
    # Returns:
    #     (bool): True if artifact was created with buildroot
    #
    def buildroot_exists(self):

        artifact = self._get_proto()
        return bool(str(artifact.buildroot))

    # cached_buildtree()
    #
    # Check if artifact is cached with expected buildtree. A
    # buildtree will not be present if the rest of the partial artifact
    # is not cached.
    #
    # Returns:
    #     (bool): True if artifact cached with buildtree, False if
    #             missing expected buildtree. Note this only confirms
    #             if a buildtree is present, not its contents.
    #
    def cached_buildtree(self):

        buildtree_digest = self._get_field_digest("buildtree")
        if buildtree_digest:
            return self._cas.contains_directory(buildtree_digest, with_files=True)
        else:
            return False

    # buildtree_exists()
    #
    # Check if artifact was created with a buildtree. This does not check
    # whether the buildtree is present in the local cache.
    #
    # Returns:
    #     (bool): True if artifact was created with buildtree
    #
    def buildtree_exists(self):

        artifact = self._get_proto()
        return bool(str(artifact.buildtree))

    # cached_sources()
    #
    # Check if artifact is cached with sources.
    #
    # Returns:
    #     (bool): True if artifact is cached with sources, False if sources
    #             are not available.
    #
    def cached_sources(self):

        sources_digest = self._get_field_digest("sources")
        if sources_digest:
            return self._cas.contains_directory(sources_digest, with_files=True)
        else:
            return False

    # load_public_data():
    #
    # Loads the public data from the cached artifact
    #
    # Returns:
    #    (dict): The artifacts cached public data
    #
    def load_public_data(self):

        # Load the public data from the artifact
        artifact = self._get_proto()
        with self._cas.open(artifact.public_data) as meta_file:
            meta_str = meta_file.read()
            data = _yaml.load_data(meta_str, file_name="public.yaml")

        return data

    # load_sandbox_config():
    #
    # Loads the sandbox configuration from the cached artifact
    #
    # Returns:
    #    The stored SandboxConfig object
    #
    def load_sandbox_config(self) -> SandboxConfig:

        # Load the sandbox data from the artifact
        artifact = self._get_proto()
        meta_file = self._cas.objpath(artifact.low_diversity_meta)
        data = _yaml.load(meta_file, shortname="low-diversity-meta.yaml")

        # Extract the sandbox data
        config = data.get_mapping("sandbox-config")

        # Return a SandboxConfig
        return SandboxConfig.new_from_node(config)

    # load_environment():
    #
    # Loads the environment variables from the cached artifact
    #
    # Returns:
    #    The environment variables
    #
    def load_environment(self) -> Dict[str, str]:

        # Load the sandbox data from the artifact
        artifact = self._get_proto()
        meta_file = self._cas.objpath(artifact.low_diversity_meta)
        data = _yaml.load(meta_file, shortname="low-diversity-meta.yaml")

        # Extract the environment
        config = data.get_mapping("environment")

        # Return the environment
        return config.strip_node_info()

    # load_variables():
    #
    # Loads the element variables from the cached artifact
    #
    # Returns:
    #    The element variables
    #
    def load_variables(self) -> Variables:

        # Load the sandbox data from the artifact
        artifact = self._get_proto()
        meta_file = self._cas.objpath(artifact.high_diversity_meta)
        data = _yaml.load(meta_file, shortname="high-diversity-meta.yaml")

        # Extract the variables node and return the new Variables instance
        variables_node = data.get_mapping("variables")
        return Variables(variables_node)

    # load_build_result():
    #
    # Load the build result from the cached artifact
    #
    # Returns:
    #    (bool): Whether the artifact of this element present in the artifact cache is of a success
    #    (str): Short description of the result
    #    (str): Detailed description of the result
    #
    def load_build_result(self):

        artifact = self._get_proto()
        build_result = (artifact.build_success, artifact.build_error, artifact.build_error_details)

        return build_result

    # get_metadata_keys():
    #
    # Retrieve the strong and weak keys from the given artifact.
    #
    # Returns:
    #    The strong key
    #    The strict key
    #    The weak key
    #
    def get_metadata_keys(self) -> Tuple[str, str, str]:

        if self._metadata_keys is not None:
            return self._metadata_keys

        # Extract proto
        artifact = self._get_proto()

        strong_key = artifact.strong_key
        strict_key = artifact.strict_key
        weak_key = artifact.weak_key

        self._metadata_keys = (strong_key, strict_key, weak_key)

        return self._metadata_keys

    # get_metadata_workspaced():
    #
    # Retrieve the hash of dependency from the given artifact.
    #
    # Returns:
    #    (bool): Whether the given artifact was workspaced
    #
    def get_metadata_workspaced(self):

        if self._metadata_workspaced is not None:
            return self._metadata_workspaced

        # Extract proto
        artifact = self._get_proto()

        self._metadata_workspaced = artifact.was_workspaced

        return self._metadata_workspaced

    # get_metadata_workspaced_dependencies():
    #
    # Retrieve the hash of workspaced dependencies keys from the given artifact.
    #
    # Returns:
    #    (list): List of which dependencies are workspaced
    #
    def get_metadata_workspaced_dependencies(self):

        if self._metadata_workspaced_dependencies is not None:
            return self._metadata_workspaced_dependencies

        # Extract proto
        artifact = self._get_proto()

        self._metadata_workspaced_dependencies = [
            dep.element_name for dep in artifact.build_deps if dep.was_workspaced
        ]

        return self._metadata_workspaced_dependencies

    # get_dependency_artifact_names()
    #
    # Retrieve the artifact names of all of the dependencies in _Scope.BUILD
    #
    # Returns:
    #    (list [str]): A list of refs of all build dependencies in staging order.
    #
    def get_dependency_artifact_names(self):
        # XXX: The pylint disable is necessary due to upstream issue:
        # https://github.com/PyCQA/pylint/issues/850
        from .element import _get_normal_name  # pylint: disable=cyclic-import

        artifact = self._get_proto()
        try:
            dependency_refs = [
                os.path.join(dep.project_name, _get_normal_name(dep.element_name), dep.cache_key)
                for dep in artifact.build_deps
            ]
        except AttributeError:
            # If the artifact has no dependencies, the build_deps attribute
            # will be missing from the proto.
            dependency_refs = []

        return dependency_refs

    # query_cache():
    #
    # Check whether the artifact corresponding to the stored cache key is
    # available. This also checks whether all required parts of the artifact
    # are available, which may depend on command and configuration. The cache
    # key used for querying is dependent on the current context.
    #
    # Returns:
    #     (bool): Whether artifact is in local cache
    #
    def query_cache(self):
        artifact = self._load_proto()
        if not artifact:
            self._cached = False
            return False

        # Check whether 'files' subdirectory is available, with or without file contents
        if str(artifact.files) and not self._cas.contains_directory(artifact.files, with_files=True):
            self._cached = False
            return False

        # Check whether public data and logs are available
        logfile_digests = [logfile.digest for logfile in artifact.logs]
        digests = [artifact.low_diversity_meta, artifact.high_diversity_meta, artifact.public_data] + logfile_digests
        if not self._cas.contains_files(digests):
            self._cached = False
            return False

        self._proto = artifact
        self._cached = True
        return True

    # cached()
    #
    # Return whether the artifact is available in the local cache. This must
    # be called after `query_cache()` or `set_cached()`.
    #
    # Returns:
    #     (bool): Whether artifact is in local cache
    #
    def cached(self, *, buildtree=False):
        assert self._cached is not None
        ret = self._cached
        if buildtree:
            ret = ret and (self.cached_buildtree() or not self.buildtree_exists())
        return ret

    # cached_logs()
    #
    # Check if the artifact is cached with log files.
    #
    # Returns:
    #     (bool): True if artifact is cached with logs, False if
    #             element not cached or missing logs.
    #
    def cached_logs(self):
        # Log files are currently considered an essential part of an artifact.
        # If the artifact is cached, its log files are available as well.
        return self._element._cached()

    # set_cached()
    #
    # Mark the artifact as cached without querying the filesystem.
    # This is used as optimization when we know the artifact is available.
    #
    def set_cached(self):
        self._proto = self._load_proto()
        assert self._proto
        self._cached = True

    # pull()
    #
    # Pull artifact from remote artifact repository into local artifact cache.
    #
    # Args:
    #     pull_buildtrees (bool): Whether to pull buildtrees or not
    #
    # Returns: True if the artifact has been downloaded, False otherwise
    #
    def pull(self, *, pull_buildtrees):
        artifacts = self._context.artifactcache

        pull_key = self.get_extract_key()

        if not artifacts.pull(self._element, pull_key, pull_buildtrees=pull_buildtrees):
            return False

        self.set_cached()

        # Add reference for the other key (weak key when pulling with strong key,
        # strong key when pulling with weak key)
        for key in self.get_metadata_keys():
            artifacts.link_key(self._element, pull_key, key)

        return True

    #  load_proto()
    #
    # Returns:
    #     (Artifact): Artifact proto
    #
    def _load_proto(self):
        key = self.get_extract_key()

        proto_path = os.path.join(self._artifactdir, self._element.get_artifact_name(key=key))
        artifact = ArtifactProto()
        try:
            with open(proto_path, mode="r+b") as f:
                artifact.ParseFromString(f.read())
        except FileNotFoundError:
            return None

        os.utime(proto_path)

        return artifact

    # _get_proto()
    #
    # Returns:
    #     (Artifact): Artifact proto
    #
    def _get_proto(self):
        return self._proto

    # _get_field_digest()
    #
    # Returns:
    #     (Digest): Digest of field specified
    #
    def _get_field_digest(self, field):
        artifact_proto = self._get_proto()
        digest = getattr(artifact_proto, field)
        if not str(digest):
            return None

        return digest
