#
#  Copyright (C) 2018 Codethink Limited
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

from .._exceptions import LoadError, LoadErrorReason
from ..node cimport MappingNode, Node, ProvenanceInformation, ScalarNode, SequenceNode


# Symbol():
#
# A simple object to denote the symbols we load with from YAML
#
class Symbol():
    FILENAME = "filename"
    KIND = "kind"
    DEPENDS = "depends"
    BUILD_DEPENDS = "build-depends"
    RUNTIME_DEPENDS = "runtime-depends"
    SOURCES = "sources"
    CONFIG = "config"
    VARIABLES = "variables"
    ENVIRONMENT = "environment"
    ENV_NOCACHE = "environment-nocache"
    PUBLIC = "public"
    TYPE = "type"
    BUILD = "build"
    RUNTIME = "runtime"
    ALL = "all"
    DIRECTORY = "directory"
    JUNCTION = "junction"
    SANDBOX = "sandbox"
    STRICT = "strict"


# Dependency()
#
# A simple object describing a dependency
#
# Args:
#    name (str or Node): The element name
#    dep_type (str): The type of dependency, can be
#                    Symbol.ALL, Symbol.BUILD, or Symbol.RUNTIME
#    junction (str): The element name of the junction, or None
#    provenance (ProvenanceInformation): The YAML node provenance of where this
#                                        dependency was declared
#
cdef class Dependency:
    cdef public ProvenanceInformation provenance
    cdef public str name
    cdef public str dep_type
    cdef public str junction
    cdef public bint strict

    def __init__(self,
                 Node dep,
                 str default_dep_type=None):
        cdef str dep_type

        self.provenance = dep.get_provenance()

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

        # Name of the element should never contain more than one `:` characters
        if self.name.count(':') > 1:
            raise LoadError("{}: Dependency {} contains multiple `:` in its name. "
                            "Recursive lookups for cross-junction elements is not "
                            "allowed.".format(self.provenance, self.name), LoadErrorReason.INVALID_DATA)

        # Attempt to split name if no junction was specified explicitly
        if not self.junction and self.name.count(':') == 1:
            self.junction, self.name = self.name.split(':')


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
        dependency = Dependency(dep_node, default_dep_type=default_dep_type)
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
