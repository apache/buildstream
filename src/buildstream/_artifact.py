#
#  Copyright (C) 2019 Codethink Limited
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
#        Tom Pollard <tom.pollard@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

"""
Artifact
=========

Implementation of the Artifact class which aims to 'abstract' direct
artifact composite interaction away from Element class

"""

import os

from ._exceptions import ArtifactError
from ._protos.buildstream.v2.artifact_pb2 import Artifact as ArtifactProto
from . import _yaml
from . import utils
from .types import Scope
from .storage._casbaseddirectory import CasBasedDirectory


# An Artifact class to abstract artifact operations
# from the Element class
#
# Args:
#     element (Element): The Element object
#     context (Context): The BuildStream context
#     strong_key (str): The elements strong cache key, dependent on context
#     weak_key (str): The elements weak cache key
#
class Artifact:

    version = 0

    def __init__(self, element, context, *, strong_key=None, weak_key=None):
        self._element = element
        self._context = context
        self._cache_key = strong_key
        self._weak_cache_key = weak_key
        self._artifactdir = context.artifactdir
        self._cas = context.get_cascache()
        self._tmpdir = context.tmpdir
        self._proto = None

        self._metadata_keys = None  # Strong and weak key tuple extracted from the artifact
        self._metadata_dependencies = None  # Dictionary of dependency strong keys from the artifact
        self._metadata_workspaced = None  # Boolean of whether it's a workspaced artifact
        self._metadata_workspaced_dependencies = None  # List of which dependencies are workspaced from the artifact
        self._cached = None  # Boolean of whether the artifact is cached

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
    #    sandbox_build_dir (Directory): Virtual Directory object for the sandbox build-root
    #    collectvdir (Directory): Virtual Directoy object from within the sandbox for collection
    #    sourcesvdir (Directory): Virtual Directoy object for the staged sources
    #    buildresult (tuple): bool, short desc and detailed desc of result
    #    publicdata (dict): dict of public data to commit to artifact metadata
    #
    # Returns:
    #    (int): The size of the newly cached artifact
    #
    def cache(self, sandbox_build_dir, collectvdir, sourcesvdir, buildresult, publicdata):

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
        artifact.weak_key = self._weak_cache_key

        artifact.was_workspaced = bool(element._get_workspace())
        properties = ["mtime"] if artifact.was_workspaced else []

        # Store files
        if collectvdir:
            filesvdir = CasBasedDirectory(cas_cache=self._cas)
            filesvdir.import_files(collectvdir, properties=properties)
            artifact.files.CopyFrom(filesvdir._get_digest())
            size += filesvdir.get_size()

        # Store public data
        with utils._tempnamedfile_name(dir=self._tmpdir) as tmpname:
            _yaml.roundtrip_dump(publicdata, tmpname)
            public_data_digest = self._cas.add_object(path=tmpname, link_directly=True)
            artifact.public_data.CopyFrom(public_data_digest)
            size += public_data_digest.size_bytes

        # store build dependencies
        for e in element.dependencies(Scope.BUILD):
            new_build = artifact.build_deps.add()
            new_build.project_name = e.project_name
            new_build.element_name = e.name
            new_build.cache_key = e._get_cache_key()
            new_build.was_workspaced = bool(e._get_workspace())

        # Store log file
        log_filename = context.messenger.get_log_filename()
        if log_filename:
            digest = self._cas.add_object(path=log_filename)
            log = artifact.logs.add()
            log.name = os.path.basename(log_filename)
            log.digest.CopyFrom(digest)
            size += log.digest.size_bytes

        # Store build tree
        if sandbox_build_dir:
            buildtreevdir = CasBasedDirectory(cas_cache=self._cas)
            buildtreevdir.import_files(sandbox_build_dir, properties=properties)
            artifact.buildtree.CopyFrom(buildtreevdir._get_digest())
            size += buildtreevdir.get_size()

        # Store sources
        if sourcesvdir:
            artifact.sources.CopyFrom(sourcesvdir._get_digest())
            size += sourcesvdir.get_size()

        os.makedirs(os.path.dirname(os.path.join(self._artifactdir, element.get_artifact_name())), exist_ok=True)
        keys = utils._deduplicate([self._cache_key, self._weak_cache_key])
        for key in keys:
            path = os.path.join(self._artifactdir, element.get_artifact_name(key=key))
            with utils.save_file_atomic(path, mode="wb") as f:
                f.write(artifact.SerializeToString())

        return size

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
        meta_file = self._cas.objpath(artifact.public_data)
        data = _yaml.load(meta_file, shortname="public.yaml")

        return data

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
    #    (str): The strong key
    #    (str): The weak key
    #
    def get_metadata_keys(self):

        if self._metadata_keys is not None:
            return self._metadata_keys

        # Extract proto
        artifact = self._get_proto()

        strong_key = artifact.strong_key
        weak_key = artifact.weak_key

        self._metadata_keys = (strong_key, weak_key)

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

    # get_dependency_refs()
    #
    # Retrieve the artifact refs of the artifact's dependencies
    #
    # Args:
    #    deps (Scope): The scope of dependencies
    #
    # Returns:
    #    (list [str]): A list of refs of all build dependencies in staging order.
    #
    def get_dependency_refs(self, deps=Scope.BUILD):
        # XXX: The pylint disable is necessary due to upstream issue:
        # https://github.com/PyCQA/pylint/issues/850
        from .element import _get_normal_name  # pylint: disable=cyclic-import

        # Extract the proto
        artifact = self._get_proto()

        if deps == Scope.BUILD:
            try:
                dependency_refs = [
                    os.path.join(dep.project_name, _get_normal_name(dep.element_name), dep.cache_key)
                    for dep in artifact.build_deps
                ]
            except AttributeError:
                # If the artifact has no dependencies
                dependency_refs = []
        elif deps == Scope.NONE:
            dependency_refs = [self._element.get_artifact_name()]
        else:
            # XXX: We can only support obtaining the build dependencies of
            #      an artifact. This is because this is the only information we store
            #      in the proto. If we were to add runtime deps to the proto, we'd need
            #      to include these in cache key calculation.
            #
            #      This would have some undesirable side effects:
            #          1. It might trigger unnecessary rebuilds.
            #          2. It would be impossible to support cyclic runtime dependencies
            #             in the future
            raise ArtifactError("Dependency scope: {} is not supported for artifacts".format(deps))

        return dependency_refs

    # cached():
    #
    # Check whether the artifact corresponding to the stored cache key is
    # available. This also checks whether all required parts of the artifact
    # are available, which may depend on command and configuration. The cache
    # key used for querying is dependent on the current context.
    #
    # Returns:
    #     (bool): Whether artifact is in local cache
    #
    def cached(self):

        if self._cached is not None:
            return self._cached

        context = self._context

        artifact = self._load_proto()
        if not artifact:
            self._cached = False
            return False

        # Determine whether directories are required
        require_directories = context.require_artifact_directories
        # Determine whether file contents are required as well
        require_files = context.require_artifact_files or self._element._artifact_files_required()

        # Check whether 'files' subdirectory is available, with or without file contents
        if (
            require_directories
            and str(artifact.files)
            and not self._cas.contains_directory(artifact.files, with_files=require_files)
        ):
            self._cached = False
            return False

        # Check whether public data and logs are available
        logfile_digests = [logfile.digest for logfile in artifact.logs]
        digests = [artifact.public_data] + logfile_digests
        if not self._cas.contains_files(digests):
            self._cached = False
            return False

        self._proto = artifact
        self._cached = True
        return True

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

    # reset_cached()
    #
    # Allow the Artifact to query the filesystem to determine whether it
    # is cached or not.
    #
    def reset_cached(self):
        self._proto = None
        self._cached = None

    # set_cached()
    #
    # Mark the artifact as cached without querying the filesystem.
    # This is used as optimization when we know the artifact is available.
    #
    def set_cached(self):
        self._proto = self._load_proto()
        self._cached = True

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
