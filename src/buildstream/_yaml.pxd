#
#  Copyright (C) 2019 Bloomberg L.P.
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
#        Benjamin Schubert <bschubert@bloomberg.net>

# Documentation for each class and method here can be found in the adjacent
# implementation file (_yaml.pyx)

cdef class Node:

    cdef public object value
    cdef public int file_index
    cdef public int line
    cdef public int column

    cpdef Node copy(self)


cdef class MappingNode(Node):
    cdef Node get(self, str key, default, default_constructor)
    cpdef MappingNode get_mapping(self, str key, default=*)
    cpdef Node get_node(self, str key, list allowed_types=*, bint allow_none=*)
    cpdef ScalarNode get_scalar(self, str key, default=*)
    cpdef SequenceNode get_sequence(self, str key, object default=*)
    cpdef bint get_bool(self, str key, default=*) except *
    cpdef int get_int(self, str key, default=*) except *
    cpdef str get_str(self, str key, object default=*)
    cpdef object items(self)
    cpdef list keys(self)
    cpdef void safe_del(self, str key)
    cpdef object values(self)


cdef class ScalarNode(Node):
    cpdef bint as_bool(self) except *
    cpdef int as_int(self) except *
    cpdef str as_str(self)
    cpdef bint is_none(self)


cdef class SequenceNode(Node):
    cpdef MappingNode mapping_at(self, int index)
    cpdef SequenceNode sequence_at(self, int index)
    cpdef list as_str_list(self)


cdef class ProvenanceInformation:

    cdef public Node node
    cdef str displayname
    cdef public str filename, shortname
    cdef public int col, line
    cdef public object project, toplevel
    cdef public bint is_synthetic


cpdef void node_validate(Node node, list valid_keys) except *
cpdef ProvenanceInformation node_get_provenance(Node node, str key=*, list indices=*)
