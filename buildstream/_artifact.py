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

from .types import _KeyStrength


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
