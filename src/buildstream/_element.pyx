from pyroaring import BitMap

from .types import Scope

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


def dependencies(element, scope, *, recurse=True, visited=None):
    # The format of visited is (BitMap(), BitMap()), with the first BitMap
    # containing element that have been visited for the `Scope.BUILD` case
    # and the second one relating to the `Scope.RUN` case.
    if not recurse:
        if scope in (SCOPE_BUILD, SCOPE_ALL):
            yield from element._Element__build_dependencies
        if scope in (SCOPE_RUN, SCOPE_ALL):
            yield from element._Element__runtime_dependencies
    else:
        if visited is None:
            # Visited is of the form (Visited for Scope.BUILD, Visited for Scope.RUN)
            visited = (BitMap(), BitMap())

        if scope == SCOPE_ALL:
            # We can use only one of the sets when checking for Scope.ALL, as we would get added to
            # both anyways.
            # This would break if we start reusing 'visited' and mixing scopes, but that is done
            # nowhere in the codebase.
            if element._unique_id not in visited[0]:
                yield from deps_visit_all(element, visited[0])
        elif scope == SCOPE_BUILD:
            if element._unique_id not in visited[0]:
                yield from deps_visit_build(element, visited[0], visited[1])
        elif scope == SCOPE_RUN:
            if element._unique_id not in visited[1]:
                yield from deps_visit_run(element, visited[1])
        else:
            yield element
