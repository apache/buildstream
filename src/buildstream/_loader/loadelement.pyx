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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

from functools import cmp_to_key

from pyroaring import BitMap, FrozenBitMap  # pylint: disable=no-name-in-module

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from ..node cimport MappingNode, Node, ProvenanceInformation, ScalarNode, SequenceNode
from .types import Symbol


# Counter to get ids to LoadElements
cdef int _counter = 0

cdef int _next_synthetic_counter():
    global _counter
    _counter += 1
    return _counter


# DependencyType
#
# A bitfield to represent dependency types
#
cpdef enum DependencyType:

    # A build dependency
    BUILD = 0x001

    # A runtime dependency
    RUNTIME = 0x002

    # Both build and runtime dependencies
    ALL = 0x003


# Some forward declared lists, avoid creating these lists repeatedly
#
cdef list _filename_allowed_types=[ScalarNode, SequenceNode]
cdef list _valid_dependency_keys = [Symbol.FILENAME, Symbol.TYPE, Symbol.JUNCTION, Symbol.STRICT, Symbol.CONFIG]
cdef list _valid_typed_dependency_keys = [Symbol.FILENAME, Symbol.JUNCTION, Symbol.STRICT, Symbol.CONFIG]
cdef list _valid_element_keys = [
    'kind', 'depends', 'sources', 'sandbox', 'variables', 'environment', 'environment-nocache',
    'config', 'public', 'description', 'build-depends', 'runtime-depends',
]


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
#    dep_type (DependencyType): the type of dependency this dependency link is
#
cdef class Dependency:
    cdef readonly LoadElement element  # The resolved LoadElement
    cdef readonly int dep_type  # The dependency type (runtime or build or both)
    cdef readonly str name  # The project local dependency name
    cdef readonly str junction  # The junction path of the dependency name, if any
    cdef readonly bint strict  # Whether this is a strict dependency
    cdef readonly list config_nodes  # The custom config nodes for Element.configure_dependencies()
    cdef readonly Node node  # The original node of the dependency

    def __cinit__(self, LoadElement element = None, int dep_type = DependencyType.ALL):
        self.element = element
        self.dep_type = dep_type
        self.name = None
        self.junction = None
        self.strict = False
        self.config_nodes = None
        self.node = None

    # path
    #
    # The path of the dependency represented as a single string,
    # instead of junction and name being separate.
    #
    @property
    def path(self):
        if self.junction is not None:
            return "{}:{}".format(self.junction, self.name)
        return self.name

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
    # Load dependency attributes from a Node, and validate it
    #
    # Args:
    #    dep (Node): A node to load the dependency from
    #    junction (str): The junction name, or None
    #    name (str): The element name
    #    default_dep_type (DependencyType): The default dependency type
    #
    cdef load(self, Node dep, str junction, str name, int default_dep_type):
        cdef str parsed_type
        cdef MappingNode config_node
        cdef ProvenanceInformation provenance

        self.junction = junction
        self.name = name
        self.node = dep
        self.element = None

        if type(dep) is ScalarNode:
            self.dep_type = default_dep_type or DependencyType.ALL

        elif type(dep) is MappingNode:
            if default_dep_type:
                (<MappingNode> dep).validate_keys(_valid_typed_dependency_keys)
                self.dep_type = default_dep_type
            else:
                (<MappingNode> dep).validate_keys(_valid_dependency_keys)

                # Resolve the DependencyType
                parsed_type = (<MappingNode> dep).get_str(<str> Symbol.TYPE, None)
                if parsed_type is None or parsed_type == <str> Symbol.ALL:
                    self.dep_type = DependencyType.ALL
                elif parsed_type == <str> Symbol.BUILD:
                    self.dep_type = DependencyType.BUILD
                elif parsed_type == <str> Symbol.RUNTIME:
                    self.dep_type = DependencyType.RUNTIME
                else:
                    provenance = dep.get_scalar(Symbol.TYPE).get_provenance()
                    raise LoadError("{}: Dependency type '{}' is not 'build', 'runtime' or 'all'"
                                    .format(provenance, parsed_type), LoadErrorReason.INVALID_DATA)

            self.strict = (<MappingNode> dep).get_bool(<str> Symbol.STRICT, False)

            config_node = (<MappingNode> dep).get_mapping(<str> Symbol.CONFIG, None)
            if config_node:
                if self.dep_type == DependencyType.RUNTIME:
                    raise LoadError("{}: Specifying 'config' for a runtime dependency is not allowed"
                                    .format(config_node.get_provenance()), LoadErrorReason.INVALID_DATA)
                self.config_nodes = [config_node]

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
            raise LoadError("{}: Dependency is not specified as a string or a dictionary".format(self.node.get_provenance()),
                            LoadErrorReason.INVALID_DATA)

        # Only build dependencies are allowed to be strict
        #
        if self.strict and self.dep_type == DependencyType.RUNTIME:
            raise LoadError("{}: Runtime dependency {} specified as `strict`.".format(self.node.get_provenance(), self.name),
                            LoadErrorReason.INVALID_DATA,
                            detail="Only dependencies required at build time may be declared `strict`.")

    # merge()
    #
    # Merge the attributes of an existing dependency into this dependency
    #
    # Args:
    #    other (Dependency): The dependency to merge into this one
    #
    cdef merge(self, Dependency other):
        self.dep_type = self.dep_type | other.dep_type
        self.strict = self.strict or other.strict

        if self.config_nodes and other.config_nodes:
            self.config_nodes.extend(other.config_nodes)
        else:
            self.config_nodes = self.config_nodes or other.config_nodes


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
    cdef readonly str description
    cdef readonly str kind
    cdef int node_id
    cdef readonly bint first_pass
    cdef readonly object _loader
    cdef readonly ScalarNode link_target
    # TODO: if/when pyroaring exports symbols, we could type this statically
    cdef object _dep_cache
    cdef readonly list dependencies
    cdef readonly bint fully_loaded  # This is True if dependencies were also loaded

    def __cinit__(self, MappingNode node, str filename, object loader):

        #
        # Public members
        #
        self.kind = None        # The Element kind
        self.node = node        # The YAML node
        self.name = filename    # The element name
        self.full_name = None   # The element full name (with associated junction)
        self.node_id = _next_synthetic_counter()
        self.link_target = None  # The target of a link element (ScalarNode)
        self.fully_loaded = False  # Whether we entered the loop to load dependencies or not

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
        self.node.validate_keys(_valid_element_keys)

        self.kind = node.get_str(Symbol.KIND, default=None)
        self.description = node.get_str(Symbol.DESCRIPTION, default=None)
        self.first_pass = self.kind in ("junction", "link")

        #
        # If this is a link, resolve it right away and just
        # store the link target and provenance
        #
        if self.kind == 'link':
            # Avoid cyclic import here
            from ..element import Element

            element = Element._new_from_load_element(self)

            # Custom error for link dependencies, since we don't completely
            # parse their dependencies we cannot rely on the built-in ElementError.
            deps = extract_depends_from_node(self.node)
            if deps:
                raise LoadError(
                    "{}: Dependencies are forbidden for 'link' elements".format(element),
                    LoadErrorReason.LINK_FORBIDDEN_DEPENDENCIES
                )

            self.link_target = element.target_node

        # We don't count progress for junction elements or link
        # as they do not represent real elements in the build graph.
        #
        # We check for a `None` kind, to avoid reporting progress for
        # the virtual toplevel element used to load the pipeline.
        #
        if self._loader.load_context.task and self.kind is not None and not self.first_pass:
            self._loader.load_context.task.add_current_progress()

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

    # mark_fully_loaded()
    #
    # Sets the fully loaded state on this load element
    #
    # This state bit is used by the Loader to distinguish
    # between an element which has only been shallow loaded
    # and an element which has entered the loop which loads
    # it's dependencies.
    #
    # Args:
    #    element (LoadElement): The resolved LoadElement
    #
    def mark_fully_loaded(self):
        self.fully_loaded = True

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


# Sort algorithm copied from Python 3.12
cdef extern from "listsort.c":
    int _list_sort(object list, object keyfunc) except -1


# This comparison function does not impose a total ordering, which means
# that the order of the sorted list depends on the order of inputs and
# implementation details of the sort algorithm. Always use the sort
# algorithm from Python 3.12 to ensure a deterministic result for a
# given input order.
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
        if dep_a.dep_type == DependencyType.RUNTIME:
            return 1
        elif dep_b.dep_type == DependencyType.RUNTIME:
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

        _list_sort(element.dependencies, cmp_to_key(_dependency_cmp))


# _parse_dependency_filename():
#
# Parse the filename of a dependency with the already provided parsed junction
# name, if any.
#
# This will validate that the filename node does not contain `:` if
# the junction is already specified, and otherwise it will appropriately
# split the filename string and decompose it into a junction and filename.
#
# Args:
#    node (ScalarNode): The ScalarNode of the filename
#    junction (str): The already parsed junction, or None
#
# Returns:
#    (str): The junction component of the dependency filename
#    (str): The filename component of the dependency filename
#
cdef tuple _parse_dependency_filename(ScalarNode node, str junction):
    cdef str name = node.as_str()

    if junction is not None:
        if ':' in name:
            raise LoadError(
                "{}: Dependency {} contains `:` in its name. "
                "`:` characters are not allowed in filename when "
                "junction attribute is specified.".format(node.get_provenance(), name),
                LoadErrorReason.INVALID_DATA)
    elif ':' in name:
        junction, name = name.rsplit(':', maxsplit=1)

    return junction, name


# _list_dependency_node_files():
#
# List the filename, junction tuples associated with a dependency node,
# this supports the `filename` attribute being expressed as a list, so
# that multiple dependencies can be expressed with the common attributes.
#
# Args:
#    node (Node): A YAML loaded dictionary
#
# Returns:
#    (list): A list of filenames for `node`
#
cdef list _list_dependency_node_files(Node node):

    cdef list files = []
    cdef str junction
    cdef tuple parsed_filename
    cdef Node filename_node
    cdef Node filename_iter
    cdef object filename_iter_object

    # The node can be a single filename declaration
    #
    if type(node) is ScalarNode:
        parsed_filename = _parse_dependency_filename(node, None)
        files.append(parsed_filename)

    # Otherwise it is a dictionary
    #
    elif type(node) is MappingNode:

        junction = (<MappingNode> node).get_str(<str> Symbol.JUNCTION, None)
        filename_node = (<MappingNode> node).get_node(<str> Symbol.FILENAME, allowed_types=_filename_allowed_types)

        if type(filename_node) is ScalarNode:
            parsed_filename = _parse_dependency_filename(filename_node, junction)
            files.append(parsed_filename)
        else:
            # The filename attribute is a list, iterate here
            for filename_iter_object in (<SequenceNode> filename_node).value:
                filename_iter = <Node> filename_iter_object

                if type(filename_iter_object) is not ScalarNode:
                    raise LoadError(
                        "{}: Expected string while parsing the filename list".format(filename_iter.get_provenance()),
                        LoadErrorReason.INVALID_DATA
                    )

                parsed_filename = _parse_dependency_filename(<ScalarNode>filename_iter, junction)
                files.append(parsed_filename)
    else:
        raise LoadError("{}: Dependency is not specified as a string or a dictionary".format(node.get_provenance()),
                        LoadErrorReason.INVALID_DATA)

    return files


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
#    default_dep_type (DependencyType): type to give to the dependency
#    acc (dict): a dict in which to add the loaded dependencies
#
cdef void _extract_depends_from_node(Node node, str key, int default_dep_type, dict acc) except *:
    cdef SequenceNode depends = node.get_sequence(key, [])
    cdef Dependency existing_dep
    cdef object dep_node_object
    cdef Node dep_node
    cdef object deptup_object
    cdef tuple deptup
    cdef str junction
    cdef str filename

    for dep_node_object in depends.value:
        dep_node = <Node> dep_node_object

        for deptup_object in _list_dependency_node_files(dep_node):
            deptup = <tuple> deptup_object
            junction = <str> deptup[0]
            filename = <str> deptup[1]

            dependency = Dependency()
            dependency.load(dep_node, junction, filename, default_dep_type)

            # Accumulate dependencies, merging any matching elements along the way
            existing_dep = <Dependency> acc.get(deptup, None)
            if existing_dep is not None:
                existing_dep.merge(dependency)
            else:
                acc[deptup] = dependency

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
    cdef dict acc = {}
    _extract_depends_from_node(node, <str> Symbol.BUILD_DEPENDS, <int> DependencyType.BUILD, acc)
    _extract_depends_from_node(node, <str> Symbol.RUNTIME_DEPENDS, <int> DependencyType.RUNTIME, acc)
    _extract_depends_from_node(node, <str> Symbol.DEPENDS, <int> 0, acc)
    return [dep for dep in acc.values()]
