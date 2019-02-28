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
from . import Scope
from .types import _KeyStrength
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
        buildtreevdir = assemblevdir.descend("buildtree", create=True)

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

        # cache_buildtrees defaults to 'always', as such the
        # default behaviour is to attempt to cache them. If only
        # caching failed artifact buildtrees, then query the build
        # result. Element types without a build-root dir will be cached
        # with an empty buildtreedir regardless of this configuration as
        # there will not be an applicable sandbox_build_dir.

        if sandbox_build_dir:
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

    # load_public_data():
    #
    # Loads the public data from the cached artifact
    #
    # Returns:
    #    (dict): The artifacts cached public data
    #
    def load_public_data(self):

        element = self._element
        assert element._cached()

        # Load the public data from the artifact
        artifact_vdir, _ = self._get_directory()
        meta_file = artifact_vdir._objpath(['meta', 'public.yaml'])
        data = _yaml.load(meta_file, shortname='meta/public.yaml')

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
        artifact_vdir, _ = self._get_directory(key)

        meta_file = artifact_vdir._objpath(['meta', 'build-result.yaml'])
        if not os.path.exists(meta_file):
            build_result = (True, "succeeded", None)
            return build_result

        data = _yaml.load(meta_file, shortname='meta/build-result.yaml')
        build_result = (data["success"], data.get("description"), data.get("detail"))

        return build_result

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
