#
#  Copyright (C) 2016-2018 Codethink Limited
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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
import itertools
from operator import itemgetter
from collections import OrderedDict

from pyroaring import BitMap  # pylint: disable=no-name-in-module

from ._exceptions import PipelineError
from ._message import Message, MessageType
from ._profile import Topics, PROFILER
from . import Scope
from ._project import ProjectRefStorage
from .types import _PipelineSelection


# Pipeline()
#
# Args:
#    project (Project): The Project object
#    context (Context): The Context object
#    artifacts (Context): The ArtifactCache object
#
class Pipeline:
    def __init__(self, context, project, artifacts):

        self._context = context  # The Context
        self._project = project  # The toplevel project

        #
        # Private members
        #
        self._artifacts = artifacts

    # load()
    #
    # Loads elements from target names.
    #
    # This function is called with a list of lists, such that multiple
    # target groups may be specified. Element names specified in `targets`
    # are allowed to be redundant.
    #
    # Args:
    #    target_groups (list of lists): Groups of toplevel targets to load
    #
    # Returns:
    #    (tuple of lists): A tuple of grouped Element objects corresponding to target_groups
    #
    def load(self, target_groups):

        # First concatenate all the lists for the loader's sake
        targets = list(itertools.chain(*target_groups))

        with PROFILER.profile(Topics.LOAD_PIPELINE, "_".join(t.replace(os.sep, "-") for t in targets)):
            elements = self._project.load_elements(targets)

            # Now create element groups to match the input target groups
            elt_iter = iter(elements)
            element_groups = [[next(elt_iter) for i in range(len(group))] for group in target_groups]

            return tuple(element_groups)

    # load_artifacts()
    #
    # Loads ArtifactElements from target artifacts.
    #
    # Args:
    #    target (list [str]): Target artifacts to load
    #
    # Returns:
    #    (list [ArtifactElement]): A list of ArtifactElement objects
    #
    def load_artifacts(self, targets):
        # XXX: This is not included as part of the "load-pipeline" profiler, we could move
        #      the profiler to Stream?
        return self._project.load_artifacts(targets)

    # resolve_elements()
    #
    # Resolve element state and cache keys.
    #
    # Args:
    #    targets (list of Element): The list of toplevel element targets
    #
    def resolve_elements(self, targets):
        with self._context.messenger.simple_task("Resolving cached state", silent_nested=True) as task:
            # We need to go through the project to access the loader
            if task:
                task.set_maximum_progress(self._project.loader.loaded)

            # XXX: Now that Element._update_state() can trigger recursive update_state calls
            # it is possible that we could get a RecursionError. However, this is unlikely
            # to happen, even for large projects (tested with the Debian stack). Although,
            # if it does become a problem we may have to set the recursion limit to a
            # greater value.
            for element in self.dependencies(targets, Scope.ALL):
                # Determine initial element state.
                element._initialize_state()

                # We may already have Elements which are cached and have their runtimes
                # cached, if this is the case, we should immediately notify their reverse
                # dependencies.
                element._update_ready_for_runtime_and_cached()

                if task:
                    task.add_current_progress()

    # check_remotes()
    #
    # Check if the target artifact is cached in any of the available remotes
    #
    # Args:
    #    targets (list [Element]): The list of element targets
    #
    def check_remotes(self, targets):
        with self._context.messenger.simple_task("Querying remotes for cached status", silent_nested=True) as task:
            task.set_maximum_progress(len(targets))

            for element in targets:
                element._cached_remotely()

                task.add_current_progress()

    # dependencies()
    #
    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    # Args:
    #    targets (list of Element): The target Elements to loop over
    #    scope (Scope): The scope to iterate over
    #    recurse (bool): Whether to recurse into dependencies
    #
    def dependencies(self, targets, scope, *, recurse=True):
        # Keep track of 'visited' in this scope, so that all targets
        # share the same context.
        visited = (BitMap(), BitMap())

        for target in targets:
            for element in target.dependencies(scope, recurse=recurse, visited=visited):
                yield element

    # plan()
    #
    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    #
    # Args:
    #    elements (list of Element): List of target elements to plan
    #
    # Returns:
    #    (list of Element): A depth sorted list of the build plan
    #
    def plan(self, elements):
        # Keep locally cached elements in the plan if remote artifact cache is used
        # to allow pulling artifact with strict cache key, if available.
        plan_cached = not self._context.get_strict() and self._artifacts.has_fetch_remotes()

        return _Planner().plan(elements, plan_cached)

    # get_selection()
    #
    # Gets a full list of elements based on a toplevel
    # list of element targets
    #
    # Args:
    #    targets (list of Element): The target Elements
    #    mode (_PipelineSelection): The PipelineSelection mode
    #
    # Various commands define a --deps option to specify what elements to
    # use in the result, this function reports a list that is appropriate for
    # the selected option.
    #
    def get_selection(self, targets, mode, *, silent=True):
        def redirect_and_log():
            # Redirect and log if permitted
            elements = []
            for t in targets:
                new_elm = t._get_source_element()
                if new_elm != t and not silent:
                    self._message(MessageType.INFO, "Element '{}' redirected to '{}'".format(t.name, new_elm.name))
                if new_elm not in elements:
                    elements.append(new_elm)
            return elements

        # Work around python not having a switch statement; this is
        # much clearer than the if/elif/else block we used to have.
        #
        # Note that the lambda is necessary so that we don't evaluate
        # all possible values at run time; that would be slow.
        return {
            _PipelineSelection.NONE: lambda: targets,
            _PipelineSelection.REDIRECT: redirect_and_log,
            _PipelineSelection.PLAN: lambda: self.plan(targets),
            _PipelineSelection.ALL: lambda: list(self.dependencies(targets, Scope.ALL)),
            _PipelineSelection.BUILD: lambda: list(self.dependencies(targets, Scope.BUILD)),
            _PipelineSelection.RUN: lambda: list(self.dependencies(targets, Scope.RUN)),
        }[mode]()

    # except_elements():
    #
    # Return what we are left with after the intersection between
    # excepted and target elements and their unique dependencies is
    # gone.
    #
    # Args:
    #    targets (list of Element): List of toplevel targetted elements
    #    elements (list of Element): The list to remove elements from
    #    except_targets (list of Element): List of toplevel except targets
    #
    # Returns:
    #    (list of Element): The elements list with the intersected
    #                       exceptions removed
    #
    def except_elements(self, targets, elements, except_targets):
        if not except_targets:
            return elements

        targeted = list(self.dependencies(targets, Scope.ALL))
        visited = []

        def find_intersection(element):
            if element in visited:
                return
            visited.append(element)

            # Intersection elements are those that are also in
            # 'targeted', as long as we don't recurse into them.
            if element in targeted:
                yield element
            else:
                for dep in element.dependencies(Scope.ALL, recurse=False):
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

            queue.extend(element.dependencies(Scope.ALL, recurse=False))

        # That looks like a lot, but overall we only traverse (part
        # of) the graph twice. This could be reduced to once if we
        # kept track of parent elements, but is probably not
        # significant.

        # Ensure that we return elements in the same order they were
        # in before.
        return [element for element in elements if element in visited]

    # add_elements()
    #
    # Add to a list of elements all elements that are not already in it
    #
    # Args:
    #    elements (list of Element): The element list
    #    add (list of Element): List of elements to add
    #
    # Returns:
    #    (list): The original elements list, with elements in add that weren't
    #            already in it added.
    def add_elements(self, elements, add):
        ret = elements[:]
        ret.extend(e for e in add if e not in ret)
        return ret

    # track_cross_junction_filter()
    #
    # Filters out elements which are across junction boundaries,
    # otherwise asserts that there are no such elements.
    #
    # This is currently assumed to be only relevant for element
    # lists targetted at tracking.
    #
    # Args:
    #    project (Project): Project used for cross_junction filtering.
    #                       All elements are expected to belong to that project.
    #    elements (list of Element): The list of elements to filter
    #    cross_junction_requested (bool): Whether the user requested
    #                                     cross junction tracking
    #
    # Returns:
    #    (list of Element): The filtered or asserted result
    #
    def track_cross_junction_filter(self, project, elements, cross_junction_requested):
        # Filter out cross junctioned elements
        if not cross_junction_requested:
            elements = self._filter_cross_junctions(project, elements)
        self._assert_junction_tracking(elements)

        return elements

    # assert_consistent()
    #
    # Asserts that the given list of elements are in a consistent state, that
    # is to say that all sources are consistent and can at least be fetched.
    #
    # Consequently it also means that cache keys can be resolved.
    #
    def assert_consistent(self, elements):
        inconsistent = []
        inconsistent_workspaced = []
        with self._context.messenger.timed_activity("Checking sources"):
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
    #    elements (list): The list of elements
    #
    def assert_sources_cached(self, elements):
        uncached = []
        with self._context.messenger.timed_activity("Checking sources"):
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

    #############################################################
    #                     Private Methods                       #
    #############################################################

    # _filter_cross_junction()
    #
    # Filters out cross junction elements from the elements
    #
    # Args:
    #    project (Project): The project on which elements are allowed
    #    elements (list of Element): The list of elements to be tracked
    #
    # Returns:
    #    (list): A filtered list of `elements` which does
    #            not contain any cross junction elements.
    #
    def _filter_cross_junctions(self, project, elements):
        return [element for element in elements if element._get_project() is project]

    # _assert_junction_tracking()
    #
    # Raises an error if tracking is attempted on junctioned elements and
    # a project.refs file is not enabled for the toplevel project.
    #
    # Args:
    #    elements (list of Element): The list of elements to be tracked
    #
    def _assert_junction_tracking(self, elements):

        # We can track anything if the toplevel project uses project.refs
        #
        if self._project.ref_storage == ProjectRefStorage.PROJECT_REFS:
            return

        # Ideally, we would want to report every cross junction element but not
        # their dependencies, unless those cross junction elements dependencies
        # were also explicitly requested on the command line.
        #
        # But this is too hard, lets shoot for a simple error.
        for element in elements:
            element_project = element._get_project()
            if element_project is not self._project:
                detail = (
                    "Requested to track sources across junction boundaries\n"
                    + "in a project which does not use project.refs ref-storage."
                )

                raise PipelineError("Untrackable sources", detail=detail, reason="untrackable-sources")

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self._context.messenger.message(Message(message_type, message, **args))


# _Planner()
#
# An internal object used for constructing build plan
# from a given resolved toplevel element, while considering what
# parts need to be built depending on build only dependencies
# being cached, and depth sorting for more efficient processing.
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
        for dep in element.dependencies(Scope.RUN, recurse=False):
            self.plan_element(dep, depth)

        # Dont try to plan builds of elements that are cached already
        if not element._cached_success():
            for dep in element.dependencies(Scope.BUILD, recurse=False):
                self.plan_element(dep, depth + 1)

        self.depth_map[element] = depth
        self.visiting_elements.remove(element)

    def plan(self, roots, plan_cached):
        for root in roots:
            self.plan_element(root, 0)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)

        # Set the depth of each element
        for index, item in enumerate(depth_sorted):
            item[0]._set_depth(index)

        return [item[0] for item in depth_sorted if plan_cached or not item[0]._cached_success()]
