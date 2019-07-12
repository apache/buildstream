#
#  Copyright (C) 2016 Codethink Limited
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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

# System imports
from itertools import count

from pyroaring import BitMap, FrozenBitMap  # pylint: disable=no-name-in-module


# LoadElement():
#
# A transient object breaking down what is loaded allowing us to
# do complex operations in multiple passes.
#
# Args:
#    node (dict): A YAML loaded dictionary
#    name (str): The element name
#    loader (Loader): The Loader object for this element
#
class LoadElement():
    # Dependency():
    #
    # A link from a LoadElement to its dependencies.
    #
    # Keeps a link to one of the current Element's dependencies, together with
    # its dependency type.
    #
    # Args:
    #    element (LoadElement): a LoadElement on which there is a dependency
    #    dep_type (str): the type of dependency this dependency link is
    class Dependency:
        def __init__(self, element, dep_type):
            self.element = element
            self.dep_type = dep_type

    _counter = count()

    def __init__(self, node, filename, loader):

        #
        # Public members
        #
        self.node = node        # The YAML node
        self.name = filename    # The element name
        self.full_name = None   # The element full name (with associated junction)
        self.meta_done = False  # If the MetaElement for this LoadElement is done
        self.node_id = next(self._counter)

        #
        # Private members
        #
        self._loader = loader   # The Loader object
        self._dep_cache = None  # The dependency cache, to speed up depends()

        #
        # Initialization
        #
        if loader.project.junction:
            # dependency is in subproject, qualify name
            self.full_name = '{}:{}'.format(loader.project.junction.name, self.name)
        else:
            # dependency is in top-level project
            self.full_name = self.name

        # Ensure the root node is valid
        self.node.validate_keys([
            'kind', 'depends', 'sources', 'sandbox',
            'variables', 'environment', 'environment-nocache',
            'config', 'public', 'description',
            'build-depends', 'runtime-depends',
        ])

        self.dependencies = []

    @property
    def junction(self):
        return self._loader.project.junction

    # depends():
    #
    # Checks if this element depends on another element, directly
    # or indirectly.
    #
    # Args:
    #    other (LoadElement): Another LoadElement
    #
    # Returns:
    #    (bool): True if this LoadElement depends on 'other'
    #
    def depends(self, other):
        self._ensure_depends_cache()
        return other.node_id in self._dep_cache

    ###########################################
    #            Private Methods              #
    ###########################################
    def _ensure_depends_cache(self):

        if self._dep_cache:
            return

        self._dep_cache = BitMap()

        for dep in self.dependencies:
            elt = dep.element

            # Ensure the cache of the element we depend on
            elt._ensure_depends_cache()

            # We depend on this element
            self._dep_cache.add(elt.node_id)

            # And we depend on everything this element depends on
            self._dep_cache.update(elt._dep_cache)

        self._dep_cache = FrozenBitMap(self._dep_cache)
