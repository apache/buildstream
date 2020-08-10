#
#  Copyright (C) 2020 Codethink Limited
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

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from ..element import Element
from ..node cimport MappingNode, Node, ProvenanceInformation, ScalarNode, SequenceNode
from .types import Symbol


# Counter to get ids to LoadElements
cdef int _counter = 0

cdef int _next_synthetic_counter():
    global _counter
    _counter += 1
    return _counter


# Dependency():
#
# Early stage data model for dependencies objects, the LoadElement has
# Dependency objects which in turn refer to other LoadElements in the data
# model.
#
# The constructor is incomplete, normally dependencies are loaded
# via the Dependency.load() API below. The constructor arguments are
# only used as a convenience to create the dummy Dependency objects
# at the toplevel of the load sequence in the Loader.
#
# Args:
#    element (LoadElement): a LoadElement on which there is a dependency
#    dep_type (str): the type of dependency this dependency link is
#
cdef class Dependency:
    cdef readonly LoadElement element  # The resolved LoadElement
    cdef readonly str dep_type  # The dependency type (runtime or build or both)
    cdef readonly str name  # The project local dependency name
    cdef readonly str junction  # The junction path of the dependency name, if any
    cdef readonly bint strict  # Whether this is a strict dependency
    cdef Node _node  # The original node of the dependency

    def __cinit__(self, element=None, dep_type=None):
        self.element = element
        self.dep_type = dep_type
        self.name = None
        self.junction = None
        self.strict = False
        self._node = None

    # provenance
    #
    # A property to return the ProvenanceInformation for this
    # dependency.
    #
    @property
    def provenance(self):
        return self._node.get_provenance()

    # set_element()
    #
    # Sets the resolved LoadElement
    #
    # When Dependencies are initially loaded, the `element` member
    # will be None until later on when the Loader loads the LoadElement
    # objects based on the Dependency `name` and `junction`, the Loader
    # will then call this to resolve the `element` member.
    #
    # Args:
    #    element (LoadElement): The resolved LoadElement
    #
    cpdef set_element(self, element: LoadElement):
        self.element = element

    # load()
    #
    # Load the dependency from a Node
    #
    # Args:
    #    dep (Node): A node to load the dependency from
    #    default_dep_type (str): The default dependency type
    #
    cdef load(self, Node dep, str default_dep_type):
        cdef str dep_type

        self._node = dep
        self.element = None

        if type(dep) is ScalarNode:
            self.name = dep.as_str()
            self.dep_type = default_dep_type
            self.junction = None
            self.strict = False

        elif type(dep) is MappingNode:
            if default_dep_type:
                (<MappingNode> dep).validate_keys(['filename', 'junction', 'strict'])
                dep_type = default_dep_type
            else:
                (<MappingNode> dep).validate_keys(['filename', 'type', 'junction', 'strict'])

                # Make type optional, for this we set it to None
                dep_type = (<MappingNode> dep).get_str(<str> Symbol.TYPE, None)
                if dep_type is None or dep_type == <str> Symbol.ALL:
                    dep_type = None
                elif dep_type not in [Symbol.BUILD, Symbol.RUNTIME]:
                    provenance = dep.get_scalar(Symbol.TYPE).get_provenance()
                    raise LoadError("{}: Dependency type '{}' is not 'build', 'runtime' or 'all'"
                                    .format(provenance, dep_type), LoadErrorReason.INVALID_DATA)

            self.name = (<MappingNode> dep).get_str(<str> Symbol.FILENAME)
            self.dep_type = dep_type
            self.junction = (<MappingNode> dep).get_str(<str> Symbol.JUNCTION, None)
            self.strict = (<MappingNode> dep).get_bool(<str> Symbol.STRICT, False)

            # Here we disallow explicitly setting 'strict' to False.
            #
            # This is in order to keep the door open to allowing the project.conf
            # set the default of dependency 'strict'-ness which might be useful
            # for projects which use mostly static linking and the like, in which
            # case we can later interpret explicitly non-strict dependencies
            # as an override of the project default.
            #
            if self.strict == False and Symbol.STRICT in dep:
                provenance = dep.get_scalar(Symbol.STRICT).get_provenance()
                raise LoadError("{}: Setting 'strict' to False is unsupported"
                                .format(provenance), LoadErrorReason.INVALID_DATA)

        else:
            raise LoadError("{}: Dependency is not specified as a string or a dictionary".format(self.provenance),
                            LoadErrorReason.INVALID_DATA)

        # Only build dependencies are allowed to be strict
        #
        if self.strict and self.dep_type == Symbol.RUNTIME:
            raise LoadError("{}: Runtime dependency {} specified as `strict`.".format(self.provenance, self.name),
                            LoadErrorReason.INVALID_DATA,
                            detail="Only dependencies required at build time may be declared `strict`.")

        # `:` characters are not allowed in filename if a junction was
        # explicitly specified
        if self.junction and ':' in self.name:
            raise LoadError("{}: Dependency {} contains `:` in its name. "
                            "`:` characters are not allowed in filename when "
                            "junction attribute is specified.".format(self.provenance, self.name),
                            LoadErrorReason.INVALID_DATA)

        # Attempt to split name if no junction was specified explicitly
        if not self.junction and ':' in self.name:
            self.junction, self.name = self.name.rsplit(':', maxsplit=1)


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
    cdef readonly str full_name
    cdef readonly str kind
    cdef int node_id
    cdef readonly bint first_pass
    cdef readonly object _loader
    cdef readonly str link_target
    cdef readonly ProvenanceInformation link_target_provenance
    # TODO: if/when pyroaring exports symbols, we could type this statically
    cdef object _dep_cache
    cdef readonly list dependencies

    def __cinit__(self, MappingNode node, str filename, object loader):

        #
        # Public members
        #
        self.kind = None        # The Element kind
        self.node = node        # The YAML node
        self.name = filename    # The element name
        self.full_name = None   # The element full name (with associated junction)
        self.node_id = _next_synthetic_counter()
        self.link_target = None  # The target of a link element
        self.link_target_provenance = None  # The provenance of the link target

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
            self.full_name = '{}:{}'.format(loader.project.junction._get_full_name(), self.name)
        else:
            # dependency is in top-level project
            self.full_name = self.name

        self.dependencies = []

        # Ensure the root node is valid
        self.node.validate_keys([
            'kind', 'depends', 'sources', 'sandbox',
            'variables', 'environment', 'environment-nocache',
            'config', 'public', 'description',
            'build-depends', 'runtime-depends',
        ])

        self.kind = node.get_str(Symbol.KIND, default=None)
        self.first_pass = self.kind in ("junction", "link")

        #
        # If this is a link, resolve it right away and just
        # store the link target and provenance
        #
        if self.kind == 'link':
            element = Element._new_from_load_element(self)
            element._initialize_state()

            # Custom error for link dependencies, since we don't completely
            # parse their dependencies we cannot rely on the built-in ElementError.
            deps = extract_depends_from_node(self.node)
            if deps:
                raise LoadError(
                    "{}: Dependencies are forbidden for 'link' elements".format(element),
                    LoadErrorReason.LINK_FORBIDDEN_DEPENDENCIES
                )

            self.link_target = element.target
            self.link_target_provenance = element.target_provenance

        # We don't count progress for junction elements or link
        # as they do not represent real elements in the build graph.
        #
        # We check for a `None` kind, to avoid reporting progress for
        # the virtual toplevel element used to load the pipeline.
        #
        if self._loader.load_context.task and self.kind is not None and not self.first_pass:
            self._loader.load_context.task.add_current_progress()

    # provenance
    #
    # A property reporting the ProvenanceInformation of the element
    #
    @property
    def provenance(self):
        return self.node.get_provenance()

    # project
    #
    # A property reporting the Project in which this element resides.
    #
    @property
    def project(self):
        return self._loader.project

    # junction
    #
    # A property reporting the junction element accessing this
    # element, if any.
    #
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
#    visited (set): a list of elements that should not be treated because
#                   because they already have been treated.
#                   This is useful when wanting to sort dependencies of
#                   multiple top level elements that might have a common
#                   part.
#
def sort_dependencies(LoadElement element, set visited):
    cdef list working_elements = [element]
    cdef Dependency dep

    if element in visited:
        return

    visited.add(element)

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


# _extract_depends_from_node():
#
# Helper for extract_depends_from_node to get dependencies of a particular type
#
# Adds to an array of Dependency objects from a given dict node 'node',
# allows both strings and dicts for expressing the dependency.
#
# After extracting depends, the symbol is deleted from the node
#
# Args:
#    node (Node): A YAML loaded dictionary
#    key (str): the key on the Node corresponding to the dependency type
#    default_dep_type (str): type to give to the dependency
#    acc (list): a list in which to add the loaded dependencies
#    rundeps (dict): a dictionary mapping dependency (junction, name) to dependency for runtime deps
#    builddeps (dict): a dictionary mapping dependency (junction, name) to dependency for build deps
#
cdef void _extract_depends_from_node(Node node, str key, str default_dep_type, list acc, dict rundeps, dict builddeps) except *:
    cdef SequenceNode depends = node.get_sequence(key, [])
    cdef Node dep_node
    cdef tuple deptup

    for dep_node in depends:
        dependency = Dependency()
        dependency.load(dep_node, default_dep_type)
        deptup = (dependency.junction, dependency.name)
        if dependency.dep_type in [Symbol.BUILD, None]:
            if deptup in builddeps:
                raise LoadError("{}: Duplicate build dependency found at {}."
                                .format(dependency.provenance, builddeps[deptup].provenance),
                                LoadErrorReason.DUPLICATE_DEPENDENCY)
            else:
                builddeps[deptup] = dependency
        if dependency.dep_type in [Symbol.RUNTIME, None]:
            if deptup in rundeps:
                raise LoadError("{}: Duplicate runtime dependency found at {}."
                                .format(dependency.provenance, rundeps[deptup].provenance),
                                LoadErrorReason.DUPLICATE_DEPENDENCY)
            else:
                rundeps[deptup] = dependency
        acc.append(dependency)

    # Now delete the field, we dont want it anymore
    node.safe_del(key)


# extract_depends_from_node():
#
# Creates an array of Dependency objects from a given dict node 'node',
# allows both strings and dicts for expressing the dependency and
# throws a comprehensive LoadError in the case that the node is malformed.
#
# After extracting depends, the symbol is deleted from the node
#
# Args:
#    node (Node): A YAML loaded dictionary
#
# Returns:
#    (list): a list of Dependency objects
#
def extract_depends_from_node(Node node):
    cdef list acc = []
    cdef dict rundeps = {}
    cdef dict builddeps = {}
    _extract_depends_from_node(node, <str> Symbol.BUILD_DEPENDS, <str> Symbol.BUILD, acc, rundeps, builddeps)
    _extract_depends_from_node(node, <str> Symbol.RUNTIME_DEPENDS, <str> Symbol.RUNTIME, acc, rundeps, builddeps)
    _extract_depends_from_node(node, <str> Symbol.DEPENDS, None, acc, rundeps, builddeps)
    return acc
