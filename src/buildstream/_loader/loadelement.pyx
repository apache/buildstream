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

from functools import cmp_to_key

from pyroaring import BitMap, FrozenBitMap  # pylint: disable=no-name-in-module

from ..node cimport MappingNode
from .types import Symbol


# Counter to get ids to LoadElements
cdef int _counter = 0

cdef int _next_synthetic_counter():
    global _counter
    _counter += 1
    return _counter


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
cdef class Dependency:
    cdef readonly LoadElement element
    cdef readonly str dep_type

    def __cinit__(self, LoadElement element, str dep_type):
        self.element = element
        self.dep_type = dep_type


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
cdef class LoadElement:

    cdef readonly MappingNode node
    cdef readonly str name
    cdef readonly full_name
    cdef public bint meta_done
    cdef int node_id
    cdef readonly object _loader
    # TODO: if/when pyroaring exports symbols, we could type this statically
    cdef object _dep_cache
    cdef readonly list dependencies

    def __cinit__(self, MappingNode node, str filename, object loader):

        #
        # Public members
        #
        self.node = node        # The YAML node
        self.name = filename    # The element name
        self.full_name = None   # The element full name (with associated junction)
        self.meta_done = False  # If the MetaElement for this LoadElement is done
        self.node_id = _next_synthetic_counter()

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
    def depends(self, LoadElement other not None):
        self._ensure_depends_cache()
        return other.node_id in self._dep_cache

    ###########################################
    #            Private Methods              #
    ###########################################
    cdef void _ensure_depends_cache(self):
        cdef Dependency dep

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


def _dependency_cmp(Dependency dep_a, Dependency dep_b):
    cdef LoadElement element_a = dep_a.element
    cdef LoadElement element_b = dep_b.element

    # Sort on inter element dependency first
    if element_a.depends(element_b):
        return 1
    elif element_b.depends(element_a):
        return -1

    # If there are no inter element dependencies, place
    # runtime only dependencies last
    if dep_a.dep_type != dep_b.dep_type:
        if dep_a.dep_type == Symbol.RUNTIME:
            return 1
        elif dep_b.dep_type == Symbol.RUNTIME:
            return -1

    # All things being equal, string comparison.
    if element_a.name > element_b.name:
        return 1
    elif element_a.name < element_b.name:
        return -1

    # Sort local elements before junction elements
    # and use string comparison between junction elements
    if element_a.junction and element_b.junction:
        if element_a.junction > element_b.junction:
            return 1
        elif element_a.junction < element_b.junction:
            return -1
    elif element_a.junction:
        return -1
    elif element_b.junction:
        return 1

    # This wont ever happen
    return 0


# sort_dependencies():
#
# Sort dependencies of each element by their dependencies,
# so that direct dependencies which depend on other direct
# dependencies (directly or indirectly) appear later in the
# list.
#
# This avoids the need for performing multiple topological
# sorts throughout the build process.
#
# Args:
#    element (LoadElement): The element to sort
#
def sort_dependencies(LoadElement element):
    cdef list working_elements = [element]
    cdef set visited = set(working_elements)
    cdef Dependency dep

    # Now dependency sort, we ensure that if any direct dependency
    # directly or indirectly depends on another direct dependency,
    # it is found later in the list.
    while working_elements:
        element = working_elements.pop()
        for dep in element.dependencies:
            if dep.element not in visited:
                visited.add(dep.element)
                working_elements.append(dep.element)

        element.dependencies.sort(key=cmp_to_key(_dependency_cmp))
