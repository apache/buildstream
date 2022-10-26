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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>
#        Tristan Maat <tristan.maat@codethink.co.uk>

import itertools

from collections import OrderedDict
from operator import itemgetter
from typing import List, Iterator
from pyroaring import BitMap  # pylint: disable=no-name-in-module

from .element import Element
from .types import _PipelineSelection, _Scope

from ._context import Context
from ._exceptions import PipelineError


# dependencies()
#
# Generator function to iterate over the dependencies of multiple
# targets in the specified scope, while guaranteeing that a given
# element is never yielded more than once.
#
# Args:
#    targets: The target Elements to loop over
#    scope: An integer value from the _Scope enum, the scope to iterate over
#    recurse: Whether to recurse into dependencies
#
# Yields:
#    Elements in the scope of the specified target elements
#
def dependencies(targets: List[Element], scope: int, *, recurse: bool = True) -> Iterator[Element]:
    # Keep track of 'visited' in this scope, so that all targets
    # share the same context.
    visited = (BitMap(), BitMap())

    for target in targets:
        for element in target._dependencies(scope, recurse=recurse, visited=visited):
            yield element


# get_selection()
#
# Gets a full list of elements based on a toplevel
# list of element targets
#
# Various commands define a --deps option to specify what elements to
# use in the result, this function reports a list that is appropriate for
# the selected option.
#
# Args:
#    context: The invocation context
#    targets: The target Elements
#    mode: A value from PipelineSelection enumeration
#    silent: Whether to silence messages
#    depth_sort: Whether to sort the elements by depth (for an optimal build plan)
#
# Returns:
#    A list of Elements appropriate for the specified selection mode
#
def get_selection(
    context: Context, targets: List[Element], mode: str, *, silent: bool = True, depth_sort: bool = False
) -> List[Element]:
    def redirect_and_log() -> List[Element]:
        # Redirect and log if permitted
        elements: List[Element] = []
        for t in targets:
            new_elm = t._get_source_element()
            if new_elm != t and not silent:
                context.messenger.info("Element '{}' redirected to '{}'".format(t.name, new_elm.name))
            if new_elm not in elements:
                elements.append(new_elm)
        return elements

    def plan_all() -> List[Element]:
        return _Planner().plan(targets)

    def plan_build() -> List[Element]:
        build_targets = list(dependencies(targets, _Scope.BUILD, recurse=False))
        return _Planner().plan(build_targets)

    selection_table = {
        _PipelineSelection.REDIRECT: redirect_and_log,
    }
    if depth_sort:
        #
        # Depth sorting is used with `bst build` and assumes a dynamic build planning
        # mode (Stream() will only mark the toplevel elements as "required", and all
        # elements will be built on demand).
        #
        # In this case, the `none` and `run` selection modes can potentially include
        # dependencies, and which ones will be dynamically resolved at build time, so
        # it is essentially equivalent to the `all` selection.
        #
        selection_table[_PipelineSelection.NONE] = plan_all
        selection_table[_PipelineSelection.ALL] = plan_all
        selection_table[_PipelineSelection.RUN] = plan_all
        selection_table[_PipelineSelection.BUILD] = plan_build
    else:
        selection_table[_PipelineSelection.NONE] = lambda: targets
        selection_table[_PipelineSelection.ALL] = lambda: list(dependencies(targets, _Scope.ALL))
        selection_table[_PipelineSelection.RUN] = lambda: list(dependencies(targets, _Scope.RUN))
        selection_table[_PipelineSelection.BUILD] = lambda: list(dependencies(targets, _Scope.BUILD))

    return selection_table[mode]()


# except_elements():
#
# This function calculates the intersection of the `except_targets`
# element dependencies and the `targets` dependencies, and removes
# that intersection from the `elements` list, returning the result.
#
# Args:
#    targets: List of toplevel targetted elements
#    elements: The list to remove elements from
#    except_targets: List of toplevel except targets
#
# Returns:
#    The elements list with the intersected exceptions removed
#
# Important notes on the behavior
# ===============================
#
#   * Except elements can be completely outside of the scope
#     of targets.
#
#   * When the dependencies of except elements intersect with
#     dependencies of targets, those dependencies are removed
#     from the result.
#
#   * If a target is found within the intersection of excepted
#     elements, that target and it's dependencies are considered
#     exempt from the exception intersection.
#
# Example:
#
#           (t1)   (e1)
#           / \     /
#         (o) (o) ( )
#         /     \ / \
#       (o)     (x) ( )
#         \     /     \
#         (o) (x)     ( )
#           \ /
#           (x)
#           / \
#         (x) (t2)
#         / \ / \
#       (x) (x) (o)
#               / \
#             (o) (o)
#
# Here we have a mockup graph with 2 target elements (t1) and (t2),
# and one except element (e1) which lies outside of the graph.
#
#  - ( ) elements are ignored, they were never in the element list
#  - (o) elements will be included in the result
#  - (x) elements are removed from the graph
#
# Note how (t2) reintroduces portions of the graph which were otherwise
# tainted by being depended on indirectly by the (e1) except element.
#
def except_elements(targets: List[Element], elements: List[Element], except_targets: List[Element]) -> List[Element]:
    if not except_targets:
        return elements

    targeted: List[Element] = list(dependencies(targets, _Scope.ALL))
    visited: List[Element] = []

    def find_intersection(element: Element) -> Iterator[Element]:
        if element in visited:
            return
        visited.append(element)

        # Intersection elements are those that are also in
        # 'targeted', as long as we don't recurse into them.
        if element in targeted:
            yield element
        else:
            for dep in element._dependencies(_Scope.ALL, recurse=False):
                yield from find_intersection(dep)

    # Build a list of 'intersection' elements, i.e. the set of
    # elements that lie on the border closest to excepted elements
    # between excepted and target elements.
    intersection = list(itertools.chain.from_iterable(find_intersection(element) for element in except_targets))

    # Now use this set of elements to traverse the targeted
    # elements, except 'intersection' elements and their unique
    # dependencies.
    queue = []
    visited = []

    queue.extend(targets)
    while queue:
        element = queue.pop()
        if element in visited or element in intersection:
            continue
        visited.append(element)

        queue.extend(element._dependencies(_Scope.ALL, recurse=False))

    # That looks like a lot, but overall we only traverse (part
    # of) the graph twice. This could be reduced to once if we
    # kept track of parent elements, but is probably not
    # significant.

    # Ensure that we return elements in the same order they were
    # in before.
    return [element for element in elements if element in visited]


# assert_consistent()
#
# Asserts that the given list of elements are in a consistent state, that
# is to say that all sources are consistent and can at least be fetched.
#
# Consequently it also means that cache keys can be resolved.
#
# Args:
#    context: The invocation context
#    elements: The elements to assert consistency on
#
# Raises:
#    PipelineError: If the elements are inconsistent.
#
def assert_consistent(context: Context, elements: List[Element]) -> None:
    inconsistent = []
    inconsistent_workspaced = []
    for element in elements:
        if not element._has_all_sources_resolved():
            if element._get_workspace():
                inconsistent_workspaced.append(element)
            else:
                inconsistent.append(element)

    if inconsistent:
        detail = "Exact versions are missing for the following elements:\n\n"
        for element in inconsistent:
            detail += "  Element: {} is inconsistent\n".format(element._get_full_name())
            for source in element.sources():
                if not source.is_resolved():
                    detail += "    {} is missing ref\n".format(source)
            detail += "\n"
        detail += "Try tracking these elements first with `bst source track`\n"
        raise PipelineError("Inconsistent pipeline", detail=detail, reason="inconsistent-pipeline")

    if inconsistent_workspaced:
        detail = "Some workspaces exist but are not closed\n" + "Try closing them with `bst workspace close`\n\n"
        for element in inconsistent_workspaced:
            detail += "  " + element._get_full_name() + "\n"
        raise PipelineError("Inconsistent pipeline", detail=detail, reason="inconsistent-pipeline-workspaced")


# assert_sources_cached()
#
# Asserts that sources for the given list of elements are cached.
#
# Args:
#    context: The invocation context
#    elements: The elements to assert cached source state for
#
# Raises:
#    PipelineError: If the elements have uncached sources
#
def assert_sources_cached(context: Context, elements: List[Element]):
    uncached = []
    with context.messenger.timed_activity("Checking sources"):
        for element in elements:
            if element._fetch_needed():
                uncached.append(element)

    if uncached:
        detail = "Sources are not cached for the following elements:\n\n"
        for element in uncached:
            detail += "  Following sources for element: {} are not cached:\n".format(element._get_full_name())
            for source in element.sources():
                if not source._is_cached():
                    detail += "    {}\n".format(source)
            detail += "\n"
        detail += (
            "Try fetching these elements first with `bst source fetch`,\n"
            + "or run this command with `--fetch` option\n"
        )
        raise PipelineError("Uncached sources", detail=detail, reason="uncached-sources")


# _Planner()
#
# An internal object used for constructing build plan
# from a given resolved toplevel element, using depth
# sorting for more efficient processing.
#
class _Planner:
    def __init__(self):
        self.depth_map = OrderedDict()
        self.visiting_elements = set()

    # Here we want to traverse the same element more than once when
    # it is reachable from multiple places, with the interest of finding
    # the deepest occurance of every element
    def plan_element(self, element, depth):
        if element in self.visiting_elements:
            # circular dependency, already being processed
            return

        prev_depth = self.depth_map.get(element)
        if prev_depth is not None and prev_depth >= depth:
            # element and dependencies already processed at equal or greater depth
            return

        self.visiting_elements.add(element)
        for dep in element._dependencies(_Scope.RUN, recurse=False):
            self.plan_element(dep, depth)

        for dep in element._dependencies(_Scope.BUILD, recurse=False):
            self.plan_element(dep, depth + 1)

        self.depth_map[element] = depth
        self.visiting_elements.remove(element)

    def plan(self, roots):
        for root in roots:
            self.plan_element(root, 0)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)

        # Set the depth of each element
        for index, item in enumerate(depth_sorted):
            item[0]._set_depth(index)

        return [item[0] for item in depth_sorted]
