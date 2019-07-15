from .node cimport MappingNode


cdef class Variables:

    cdef MappingNode original
    cdef dict _expstr_map
    cdef public dict flat

    cpdef str subst(self, str string)
    cdef dict _resolve(self, MappingNode node)
    cdef dict _flatten(self)