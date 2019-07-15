from pyroaring import BitMap

from .node cimport MappingNode, SequenceNode
from .types import Scope
from ._variables cimport Variables


# FIXME: we should make those as enums consumable from Cython
cdef SCOPE_ALL = Scope.ALL
cdef SCOPE_BUILD = Scope.BUILD
cdef SCOPE_RUN = Scope.RUN


def deps_visit_run(element, visited):
    visited.add(element._unique_id)

    for dep in element._Element__runtime_dependencies:
        if dep._unique_id not in visited:
            yield from deps_visit_run(dep, visited)

    yield element


def deps_visit_build(element, visited_build, visited_run):
    visited_build.add(element._unique_id)

    for dep in element._Element__build_dependencies:
        if dep._unique_id not in visited_run:
            yield from deps_visit_run(dep, visited_run)


def deps_visit_all(element, visited):
    visited.add(element._unique_id)

    for dep in element._Element__build_dependencies:
        if dep._unique_id not in visited:
            yield from deps_visit_all(dep, visited)

    for dep in element._Element__runtime_dependencies:
        if dep._unique_id not in visited:
            yield from deps_visit_all(dep, visited)

    yield element


def dependencies(element, scope, *, recurse=True):
    # The format of visited is (BitMap(), BitMap()), with the first BitMap
    # containing element that have been visited for the `Scope.BUILD` case
    # and the second one relating to the `Scope.RUN` case.
    if not recurse:
        if scope in (SCOPE_BUILD, SCOPE_ALL):
            yield from element._Element__build_dependencies
        if scope in (SCOPE_RUN, SCOPE_ALL):
            yield from element._Element__runtime_dependencies
    else:
        if scope == SCOPE_ALL:
            yield from deps_visit_all(element, BitMap())
        elif scope == SCOPE_BUILD:
            yield from deps_visit_build(element, BitMap(), BitMap())
        elif scope == SCOPE_RUN:
            yield from deps_visit_run(element, BitMap())
        else:
            yield element


def dependencies_for_targets(elements, scope):
    if scope == SCOPE_ALL:
        visited = BitMap()

        for element in elements:
            if element._unique_id not in visited:
                yield from deps_visit_all(element, visited)

    elif scope == SCOPE_BUILD:
        visited_build = BitMap()
        visited_run = BitMap()

        for element in elements:
            if element._unique_id not in visited_build:
                yield from deps_visit_build(element, visited_build, visited_run)

    elif scope == SCOPE_RUN:
        visited = BitMap()

        for element in elements:
            if element._unique_id not in visited:
                yield from deps_visit_run(element, visited)

    else:
        yield from elements


def expand_splits(Variables variables, MappingNode element_public):
    cdef MappingNode element_bst = element_public.get_mapping('bst', default={})
    cdef MappingNode element_splits = element_bst.get_mapping('split-rules', default={})

    cdef str domain
    cdef SequenceNode split_nodes
    cdef list splits

    # Resolve any variables in the public split rules directly
    for domain, split_nodes in element_splits.items():
        splits = [
            variables.subst((<str> split).strip())
            for split in split_nodes.as_str_list()
        ]
        element_splits[domain] = splits

    return element_public