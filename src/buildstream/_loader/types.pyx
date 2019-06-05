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
from .. cimport _yaml


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
    cdef public _yaml.ProvenanceInformation provenance
    cdef public str name
    cdef public str dep_type
    cdef public str junction

    def __init__(self,
                 object dep,
                 _yaml.ProvenanceInformation provenance,
                 str default_dep_type=None):
        cdef str dep_type

        self.provenance = provenance

        if type(dep) is str:
            self.name = <str> dep
            self.dep_type = default_dep_type
            self.junction = None

        elif type(dep) is _yaml.Node and type(dep.value) is dict:
            if default_dep_type:
                _yaml.node_validate(<_yaml.Node> dep, ['filename', 'junction'])
                dep_type = default_dep_type
            else:
                _yaml.node_validate(<_yaml.Node> dep, ['filename', 'type', 'junction'])

                # Make type optional, for this we set it to None
                dep_type = <str> _yaml.node_get(<_yaml.Node> dep, str, <str> Symbol.TYPE, None, None)
                if dep_type is None or dep_type == <str> Symbol.ALL:
                    dep_type = None
                elif dep_type not in [Symbol.BUILD, Symbol.RUNTIME]:
                    provenance = _yaml.node_get_provenance(dep, key=Symbol.TYPE)
                    raise LoadError(LoadErrorReason.INVALID_DATA,
                                    "{}: Dependency type '{}' is not 'build', 'runtime' or 'all'"
                                    .format(provenance, dep_type))

            self.name = <str> _yaml.node_get(<_yaml.Node> dep, str, <str> Symbol.FILENAME)
            self.dep_type = dep_type
            self.junction = <str> _yaml.node_get(<_yaml.Node> dep, str, <str> Symbol.JUNCTION, None, None)

        else:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dependency is not specified as a string or a dictionary".format(provenance))

        # `:` characters are not allowed in filename if a junction was
        # explicitly specified
        if self.junction and ':' in self.name:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dependency {} contains `:` in its name. "
                            "`:` characters are not allowed in filename when "
                            "junction attribute is specified.".format(self.provenance, self.name))

        # Name of the element should never contain more than one `:` characters
        if self.name.count(':') > 1:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dependency {} contains multiple `:` in its name. "
                            "Recursive lookups for cross-junction elements is not "
                            "allowed.".format(self.provenance, self.name))

        # Attempt to split name if no junction was specified explicitly
        if not self.junction and self.name.count(':') == 1:
            self.junction, self.name = self.name.split(':')


# extract_depends_from_node():
#
# Creates an array of Dependency objects from a given dict node 'node',
# allows both strings and dicts for expressing the dependency and
# throws a comprehensive LoadError in the case that the node is malformed.
#
# After extracting depends, the symbol is deleted from the node
#
# Args:
#    node (dict): A YAML loaded dictionary
#
# Returns:
#    (list): a list of Dependency objects
#
def extract_depends_from_node(node, *, key=None):
    if key is None:
        build_depends = extract_depends_from_node(node, key=Symbol.BUILD_DEPENDS)
        runtime_depends = extract_depends_from_node(node, key=Symbol.RUNTIME_DEPENDS)
        depends = extract_depends_from_node(node, key=Symbol.DEPENDS)
        return build_depends + runtime_depends + depends
    elif key == Symbol.BUILD_DEPENDS:
        default_dep_type = Symbol.BUILD
    elif key == Symbol.RUNTIME_DEPENDS:
        default_dep_type = Symbol.RUNTIME
    elif key == Symbol.DEPENDS:
        default_dep_type = None
    else:
        assert False, "Unexpected value of key '{}'".format(key)

    depends = _yaml.node_get(node, list, key, None, [])
    output_deps = []

    for index, dep in enumerate(depends):
        dep_provenance = _yaml.node_get_provenance(node, key=key, indices=[index])
        dependency = Dependency(dep, dep_provenance, default_dep_type=default_dep_type)
        output_deps.append(dependency)

    # Now delete the field, we dont want it anymore
    _yaml.node_del(node, key, safe=True)

    return output_deps
