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
#        Benjamin Schubert <bschubert@bloomberg.net>

# Documentation for each class and method here can be found in the adjacent
# implementation file (_yaml.pyx)

cdef class Node:

    cdef int file_index
    cdef int line
    cdef int column

    # Public Methods
    cpdef Node clone(self)
    cpdef ProvenanceInformation get_provenance(self)
    cpdef object strip_node_info(self)

    # Private Methods used in BuildStream
    cpdef void _assert_fully_composited(self) except *

    # Protected Methods
    cdef void _compose_on(self, str key, MappingNode target, list path) except *
    cdef bint _is_composite_list(self) except *
    cdef bint _shares_position_with(self, Node target)
    cdef bint _walk_find(self, Node target, list path) except *


cdef class MappingNode(Node):
    cdef dict value

    # Public Methods
    cpdef bint get_bool(self, str key, default=*) except *
    cpdef object get_enum(self, str key, object constraint, object default=*)
    cpdef object get_int(self, str key, default=*)
    cpdef MappingNode get_mapping(self, str key, default=*)
    cpdef Node get_node(self, str key, list allowed_types=*, bint allow_none=*)
    cpdef ScalarNode get_scalar(self, str key, default=*)
    cpdef SequenceNode get_sequence(self, str key, object default=*, list allowed_types=*)
    cpdef str get_str(self, str key, object default=*)
    cpdef list get_str_list(self, str key, object default=*)
    cpdef object items(self)
    cpdef list keys(self)
    cpdef void safe_del(self, str key)
    cpdef void validate_keys(self, list valid_keys) except *
    cpdef object values(self)

    # Private Methods used in BuildStream
    cpdef void _composite(self, MappingNode target) except *
    cpdef void _composite_under(self, MappingNode target) except *
    cpdef list _find(self, Node target)

    # Protected Methods
    cdef void _compose_on_composite_dict(self, MappingNode target)
    cdef void _compose_on_list(self, SequenceNode target)

    # Private Methods
    cdef void __composite(self, MappingNode target, list path) except *
    cdef Node _get(self, str key, default, default_constructor)


cdef class ScalarNode(Node):
    cdef str value

    # Public Methods
    cpdef bint as_bool(self) except *
    cpdef object as_enum(self, object constraint)
    cpdef int as_int(self) except *
    cpdef str as_str(self)
    cpdef bint is_none(self)


cdef class SequenceNode(Node):
    cdef list value

    # Public Methods
    cpdef void append(self, object value)
    cpdef list as_str_list(self)
    cpdef MappingNode mapping_at(self, int index)
    cpdef Node node_at(self, int index, list allowed_types=*)
    cpdef ScalarNode scalar_at(self, int index)
    cpdef SequenceNode sequence_at(self, int index)


cdef class ProvenanceInformation:

    cdef readonly Node _node
    cdef readonly Node _toplevel
    cdef readonly _project
    cdef readonly bint _is_synthetic
    cdef readonly str _filename
    cdef readonly str _displayname
    cdef readonly str _shortname
    cdef readonly int _col
    cdef readonly int _line


cdef int _SYNTHETIC_FILE_INDEX
cdef Py_ssize_t _create_new_file(str filename, str shortname, str displayname, object project)
cdef void _set_root_node_for_file(Py_ssize_t file_index, MappingNode contents) except *
