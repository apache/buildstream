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
import shutil

from . import _yaml
from ._exceptions import ArtifactError
from .types import Scope, _KeyStrength
from .storage._casbaseddirectory import CasBasedDirectory


# An Artifact class to abtract artifact operations
# from the Element class
#
# Args:
#     element (Element): The Element object
#     context (Context): The BuildStream context
#
class Artifact():

    def __init__(self, element, context):
        self._element = element
        self._context = context
        self._artifacts = context.artifactcache

    # get_files():
    #
    # Get a virtual directory for the artifact files content
    #
    # Args:
    #    key (str): The key for the artifact to extract,
    #               or None for the default key
    #
    # Returns:
    #    (Directory): The virtual directory object
    #    (str): The chosen key
    #
    def get_files(self, key=None):
        subdir = "files"

        return self._get_subdirectory(subdir, key)

    # get_buildtree():
    #
    # Get a virtual directory for the artifact buildtree content
    #
    # Args:
    #    key (str): The key for the artifact to extract,
    #               or None for the default key
    #
    # Returns:
    #    (Directory): The virtual directory object
    #    (str): The chosen key
    #
    def get_buildtree(self, key=None):
        subdir = "buildtree"

        return self._get_subdirectory(subdir, key)

    # get_extract_key():
    #
    # Get the key used to extract the artifact
    #
    # Returns:
    #    (str): The key
    #
    def get_extract_key(self):

        element = self._element
        context = self._context

        # Use weak cache key, if context allows use of weak cache keys
        key_strength = _KeyStrength.STRONG
        key = element._get_cache_key(strength=key_strength)
        if not context.get_strict() and not key:
            key = element._get_cache_key(strength=_KeyStrength.WEAK)

        return key

    # cache():
    #
    # Create the artifact and commit to cache
    #
    # Args:
    #    rootdir (str): An absolute path to the temp rootdir for artifact construct
    #    sandbox_build_dir (Directory): Virtual Directory object for the sandbox build-root
    #    collectvdir (Directory): Virtual Directoy object from within the sandbox for collection
    #    buildresult (tuple): bool, short desc and detailed desc of result
    #    keys (list): list of keys for the artifact commit metadata
    #    publicdata (dict): dict of public data to commit to artifact metadata
    #
    # Returns:
    #    (int): The size of the newly cached artifact
    #
    def cache(self, rootdir, sandbox_build_dir, collectvdir, buildresult, keys, publicdata):

        context = self._context
        element = self._element

        assemblevdir = CasBasedDirectory(cas_cache=self._artifacts.cas)
        logsvdir = assemblevdir.descend("logs", create=True)
        metavdir = assemblevdir.descend("meta", create=True)

        # Create artifact directory structure
        assembledir = os.path.join(rootdir, 'artifact')
        logsdir = os.path.join(assembledir, 'logs')
        metadir = os.path.join(assembledir, 'meta')
        os.mkdir(assembledir)
        os.mkdir(logsdir)
        os.mkdir(metadir)

        if collectvdir is not None:
            filesvdir = assemblevdir.descend("files", create=True)
            filesvdir.import_files(collectvdir)

        if sandbox_build_dir:
            buildtreevdir = assemblevdir.descend("buildtree", create=True)
            buildtreevdir.import_files(sandbox_build_dir)

        # Write some logs out to normal directories: logsdir and metadir
        # Copy build log
        log_filename = context.get_log_filename()
        element._build_log_path = os.path.join(logsdir, 'build.log')
        if log_filename:
            shutil.copyfile(log_filename, element._build_log_path)

        # Store public data
        _yaml.dump(_yaml.node_sanitize(publicdata), os.path.join(metadir, 'public.yaml'))

        # Store result
        build_result_dict = {"success": buildresult[0], "description": buildresult[1]}
        if buildresult[2] is not None:
            build_result_dict["detail"] = buildresult[2]
        _yaml.dump(build_result_dict, os.path.join(metadir, 'build-result.yaml'))

        # Store keys.yaml
        _yaml.dump(_yaml.node_sanitize({
            'strong': element._get_cache_key(),
            'weak': element._get_cache_key(_KeyStrength.WEAK),
        }), os.path.join(metadir, 'keys.yaml'))

        # Store dependencies.yaml
        _yaml.dump(_yaml.node_sanitize({
            e.name: e._get_cache_key() for e in element.dependencies(Scope.BUILD)
        }), os.path.join(metadir, 'dependencies.yaml'))

        # Store workspaced.yaml
        _yaml.dump(_yaml.node_sanitize({
            'workspaced': bool(element._get_workspace())
        }), os.path.join(metadir, 'workspaced.yaml'))

        # Store workspaced-dependencies.yaml
        _yaml.dump(_yaml.node_sanitize({
            'workspaced-dependencies': [
                e.name for e in element.dependencies(Scope.BUILD)
                if e._get_workspace()
            ]
        }), os.path.join(metadir, 'workspaced-dependencies.yaml'))

        metavdir.import_files(metadir)
        logsvdir.import_files(logsdir)

        artifact_size = assemblevdir.get_size()
        self._artifacts.commit(element, assemblevdir, keys)

        return artifact_size

    # cached_buildtree()
    #
    # Check if artifact is cached with expected buildtree. A
    # buildtree will not be present if the res tof the partial artifact
    # is not cached.
    #
    # Returns:
    #     (bool): True if artifact cached with buildtree, False if
    #             element not cached or missing expected buildtree.
    #             Note this only confirms if a buildtree is present,
    #             not its contents.
    #
    def cached_buildtree(self):

        context = self._context
        element = self._element

        if not element._cached():
            return False

        key_strength = _KeyStrength.STRONG if context.get_strict() else _KeyStrength.WEAK
        if not self._artifacts.contains_subdir_artifact(element, element._get_cache_key(strength=key_strength),
                                                        'buildtree'):
            return False

        return True

    # buildtree_exists()
    #
    # Check if artifact was created with a buildtree. This does not check
    # whether the buildtree is present in the local cache.
    #
    # Returns:
    #     (bool): True if artifact was created with buildtree
    #
    def buildtree_exists(self):

        if not self._element._cached():
            return False

        artifact_vdir, _ = self._get_directory()
        return artifact_vdir._exists('buildtree')

    # load_public_data():
    #
    # Loads the public data from the cached artifact
    #
    # Returns:
    #    (dict): The artifacts cached public data
    #
    def load_public_data(self):

        # Load the public data from the artifact
        meta_vdir, _ = self._get_subdirectory('meta')
        meta_file = meta_vdir._objpath('public.yaml')
        data = _yaml.load(meta_file, shortname='public.yaml')

        return data

    # load_build_result():
    #
    # Load the build result from the cached artifact
    #
    # Args:
    #    key (str): The key for the artifact to extract
    #
    # Returns:
    #    (bool): Whether the artifact of this element present in the artifact cache is of a success
    #    (str): Short description of the result
    #    (str): Detailed description of the result
    #
    def load_build_result(self, key):

        assert key is not None
        meta_vdir, _ = self._get_subdirectory('meta', key)

        meta_file = meta_vdir._objpath('build-result.yaml')
        if not os.path.exists(meta_file):
            build_result = (True, "succeeded", None)
            return build_result

        data = _yaml.load(meta_file, shortname='build-result.yaml')

        success = _yaml.node_get(data, bool, 'success')
        description = _yaml.node_get(data, str, 'description', default_value=None)
        detail = _yaml.node_get(data, str, 'detail', default_value=None)

        build_result = (success, description, detail)

        return build_result

    # get_metadata_keys():
    #
    # Retrieve the strong and weak keys from the given artifact.
    #
    # Args:
    #    key (str): The artifact key, or None for the default key
    #    metadata_keys (dict): The elements cached strong/weak
    #                          metadata keys, empty if not yet cached
    #
    # Returns:
    #    (str): The strong key
    #    (str): The weak key
    #    (dict): The key dict, None if not updated
    #
    def get_metadata_keys(self, key, metadata_keys):

        # Now extract it and possibly derive the key
        artifact_vdir, key = self._get_directory(key)

        # Now try the cache, once we're sure about the key
        if key in metadata_keys:
            return (metadata_keys[key]['strong'],
                    metadata_keys[key]['weak'], None)

        # Parse the expensive yaml now and cache the result
        meta_file = artifact_vdir._objpath('meta', 'keys.yaml')
        meta = _yaml.load(meta_file, shortname='meta/keys.yaml')
        strong_key = _yaml.node_get(meta, str, 'strong')
        weak_key = _yaml.node_get(meta, str, 'weak')

        assert key in (strong_key, weak_key)

        metadata_keys[strong_key] = _yaml.node_sanitize(meta)
        metadata_keys[weak_key] = _yaml.node_sanitize(meta)

        return (strong_key, weak_key, metadata_keys)

    # get_metadata_dependencies():
    #
    # Retrieve the hash of dependency keys from the given artifact.
    #
    # Args:
    #    key (str): The artifact key, or None for the default key
    #    metadata_dependencies (dict): The elements cached dependency metadata keys,
    #                                  empty if not yet cached
    #    metadata_keys (dict): The elements cached strong/weak
    #                          metadata keys, empty if not yet cached
    #
    # Returns:
    #    (dict): A dictionary of element names and their keys
    #    (dict): The depedencies key dict, None if not updated
    #    (dict): The elements key dict, None if not updated
    #
    def get_metadata_dependencies(self, key, metadata_dependencies, metadata_keys):

        # Extract it and possibly derive the key
        artifact_vdir, key = self._get_directory(key)

        # Now try the cache, once we're sure about the key
        if key in metadata_dependencies:
            return (metadata_dependencies[key], None, None)

        # Parse the expensive yaml now and cache the result
        meta_file = artifact_vdir._objpath('meta', 'dependencies.yaml')
        meta = _yaml.load(meta_file, shortname='meta/dependencies.yaml')

        # Cache it under both strong and weak keys
        strong_key, weak_key, metadata_keys = self.get_metadata_keys(key, metadata_keys)
        metadata_dependencies[strong_key] = _yaml.node_sanitize(meta)
        metadata_dependencies[weak_key] = _yaml.node_sanitize(meta)

        return (meta, metadata_dependencies, metadata_keys)

    # get_metadata_workspaced():
    #
    # Retrieve the hash of dependency from the given artifact.
    #
    # Args:
    #    key (str): The artifact key, or None for the default key
    #    meta_data_workspaced (dict): The elements cached boolean metadata
    #                                 of whether it's workspaced, empty if
    #                                 not yet cached
    #    metadata_keys (dict): The elements cached strong/weak
    #                          metadata keys, empty if not yet cached
    #
    # Returns:
    #    (bool): Whether the given artifact was workspaced
    #    (dict): The workspaced key dict, None if not updated
    #    (dict): The elements key dict, None if not updated
    #
    def get_metadata_workspaced(self, key, metadata_workspaced, metadata_keys):

        # Extract it and possibly derive the key
        artifact_vdir, key = self._get_directory(key)

        # Now try the cache, once we're sure about the key
        if key in metadata_workspaced:
            return (metadata_workspaced[key], None, None)

        # Parse the expensive yaml now and cache the result
        meta_file = artifact_vdir._objpath('meta', 'workspaced.yaml')
        meta = _yaml.load(meta_file, shortname='meta/workspaced.yaml')
        workspaced = _yaml.node_get(meta, bool, 'workspaced')

        # Cache it under both strong and weak keys
        strong_key, weak_key, metadata_keys = self.get_metadata_keys(key, metadata_keys)
        metadata_workspaced[strong_key] = workspaced
        metadata_workspaced[weak_key] = workspaced

        return (workspaced, metadata_workspaced, metadata_keys)

    # get_metadata_workspaced_dependencies():
    #
    # Retrieve the hash of workspaced dependencies keys from the given artifact.
    #
    # Args:
    #    key (str): The artifact key, or None for the default key
    #    metadata_workspaced_dependencies (dict): The elements cached metadata of
    #                                             which dependencies are workspaced,
    #                                             empty if not yet cached
    #    metadata_keys (dict): The elements cached strong/weak
    #                           metadata keys, empty if not yet cached
    #
    # Returns:
    #    (list): List of which dependencies are workspaced
    #    (dict): The workspaced depedencies key dict, None if not updated
    #    (dict): The elements key dict, None if not updated
    #
    def get_metadata_workspaced_dependencies(self, key, metadata_workspaced_dependencies,
                                             metadata_keys):

        # Extract it and possibly derive the key
        artifact_vdir, key = self._get_directory(key)

        # Now try the cache, once we're sure about the key
        if key in metadata_workspaced_dependencies:
            return (metadata_workspaced_dependencies[key], None, None)

        # Parse the expensive yaml now and cache the result
        meta_file = artifact_vdir._objpath('meta', 'workspaced-dependencies.yaml')
        meta = _yaml.load(meta_file, shortname='meta/workspaced-dependencies.yaml')
        workspaced = _yaml.node_sanitize(_yaml.node_get(meta, list, 'workspaced-dependencies'))

        # Cache it under both strong and weak keys
        strong_key, weak_key, metadata_keys = self.get_metadata_keys(key, metadata_keys)
        metadata_workspaced_dependencies[strong_key] = workspaced
        metadata_workspaced_dependencies[weak_key] = workspaced
        return (workspaced, metadata_workspaced_dependencies, metadata_keys)

    # cached():
    #
    # Check whether the artifact corresponding to the specified cache key is
    # available. This also checks whether all required parts of the artifact
    # are available, which may depend on command and configuration.
    #
    # This is used by _update_state() to set __strong_cached and __weak_cached.
    #
    # Args:
    #     key (str): The artifact key
    #
    # Returns:
    #     (bool): Whether artifact is in local cache
    #
    def cached(self, key):
        context = self._context

        try:
            vdir, _ = self._get_directory(key)
        except ArtifactError:
            # Either ref or top-level artifact directory missing
            return False

        # Check whether all metadata is available
        metadigest = vdir._get_child_digest('meta')
        if not self._artifacts.cas.contains_directory(metadigest, with_files=True):
            return False

        # Additional checks only relevant if artifact was created with 'files' subdirectory
        if vdir._exists('files'):
            # Determine whether directories are required
            require_directories = context.require_artifact_directories
            # Determine whether file contents are required as well
            require_files = context.require_artifact_files or self._element._artifact_files_required()

            filesdigest = vdir._get_child_digest('files')

            # Check whether 'files' subdirectory is available, with or without file contents
            if (require_directories and
                    not self._artifacts.cas.contains_directory(filesdigest, with_files=require_files)):
                return False

        return True

    # cached_logs()
    #
    # Check if the artifact is cached with log files.
    #
    # Args:
    #     key (str): The artifact key
    #
    # Returns:
    #     (bool): True if artifact is cached with logs, False if
    #             element not cached or missing logs.
    #
    def cached_logs(self, key=None):
        if not self._element._cached():
            return False

        log_vdir, _ = self._get_subdirectory('logs', key)

        logsdigest = log_vdir._get_digest()
        return self._artifacts.cas.contains_directory(logsdigest, with_files=True)

    # _get_directory():
    #
    # Get a virtual directory for the artifact contents
    #
    # Args:
    #    key (str): The key for the artifact to extract,
    #               or None for the default key
    #
    # Returns:
    #    (Directory): The virtual directory object
    #    (str): The chosen key
    #
    def _get_directory(self, key=None):

        element = self._element

        if key is None:
            key = self.get_extract_key()

        return (self._artifacts.get_artifact_directory(element, key), key)

    # _get_subdirectory():
    #
    # Get a virtual directory for the artifact subdir contents
    #
    # Args:
    #    subdir (str): The specific artifact subdir
    #    key (str): The key for the artifact to extract,
    #               or None for the default key
    #
    # Returns:
    #    (Directory): The virtual subdirectory object
    #    (str): The chosen key
    #
    def _get_subdirectory(self, subdir, key=None):

        artifact_vdir, key = self._get_directory(key)
        sub_vdir = artifact_vdir.descend(subdir)

        return (sub_vdir, key)
