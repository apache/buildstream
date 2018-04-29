#!/usr/bin/env python3
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

import itertools
from operator import itemgetter

from ._exceptions import PipelineError
from ._message import Message, MessageType
from ._loader import Loader
from .element import Element
from . import Scope, Consistency
from ._platform import Platform
from ._project import ProjectRefStorage
from ._artifactcache.artifactcache import ArtifactCacheSpec, configured_remote_artifact_cache_specs


# PipelineSelection()
#
# Defines the kind of pipeline selection to make when the pipeline
# is provided a list of targets, for whichever purpose.
#
# These values correspond to the CLI `--deps` arguments for convenience.
#
class PipelineSelection():

    # Select only the target elements in the associated targets
    NONE = 'none'

    # Select elements which must be built for the associated targets to be built
    PLAN = 'plan'

    # All dependencies of all targets, including the targets
    ALL = 'all'

    # All direct build dependencies and their recursive runtime dependencies,
    # excluding the targets
    BUILD = 'build'

    # All direct runtime dependencies and their recursive runtime dependencies,
    # including the targets
    RUN = 'run'


# Pipeline()
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    target (str): A bst filename relative to the project directory
#    inconsistent (bool): Whether to load the pipeline in a forcefully inconsistent state,
#                         this is appropriate when source tracking will run and the
#                         current source refs will not be the effective refs.
#    rewritable (bool): Whether the loaded files should be rewritable
#                       this is a bit more expensive due to deep copies
#    use_configured_remote_caches (bool): Whether to connect to configured artifact remotes.
#    add_remote_cache (str): Adds an additional artifact remote URL, which is
#                            prepended to the list of remotes (and thus given highest priority).
#
# The ticker methods will be called with an element name for each tick, a final
# tick with None as the argument is passed to signal that processing of this
# stage has terminated.
#
# Raises:
#    LoadError
#    PluginError
#    SourceError
#    ElementError
#    ProgramNotFoundError
#
class Pipeline():

    def __init__(self, context, project, targets, except_, rewritable=False):

        self.context = context     # The Context
        self.project = project     # The toplevel project
        self.targets = []          # List of toplevel target Element objects

        #
        # Private members
        #
        self._artifacts = None
        self._loader = None
        self._exceptions = None
        self._track_cross_junctions = False
        self._track_elements = []

        #
        # Early initialization
        #

        # Load selected platform
        Platform.create_instance(context, project)
        platform = Platform.get_platform()
        self._artifacts = platform.artifactcache
        self._loader = Loader(self.context, self.project, targets + except_)

        with self.context.timed_activity("Loading pipeline", silent_nested=True):
            meta_elements = self._loader.load(rewritable, None)

        # Resolve the real elements now that we've loaded the project
        with self.context.timed_activity("Resolving pipeline"):
            resolved_elements = [
                Element._new_from_meta(meta, self._artifacts)
                for meta in meta_elements
            ]

        # Now warn about any redundant source references which may have
        # been discovered in the resolve() phase.
        redundant_refs = Element._get_redundant_source_refs()
        if redundant_refs:
            detail = "The following inline specified source references will be ignored:\n\n"
            lines = [
                "{}:{}".format(source._get_provenance(), ref)
                for source, ref in redundant_refs
            ]
            detail += "\n".join(lines)
            self._message(MessageType.WARN, "Ignoring redundant source references", detail=detail)

        self.targets = resolved_elements[:len(targets)]
        self._exceptions = resolved_elements[len(targets):]

    # initialize()
    #
    # Initialize the pipeline
    #
    # Args:
    #    use_configured_remote_caches (bool): Whether to contact configured remote artifact caches
    #    add_remote_cache (str): The URL for an additional remote artifact cache
    #    track_element (list of Elements): List of elements specified by the frontend for tracking
    #    track_cross_junctions (bool): Whether tracking is allowed to cross junction boundaries
    #    track_selection (PipelineSelection): The selection algorithm for track elements
    #
    def initialize(self,
                   use_configured_remote_caches=False,
                   add_remote_cache=None,
                   track_elements=None,
                   track_cross_junctions=False,
                   track_selection=PipelineSelection.ALL):

        # Preflight directly, before ever interrogating caches or anything.
        self._preflight()

        # Initialize remote artifact caches. We allow the commandline to override
        # the user config in some cases (for example `bst push --remote=...`).
        has_remote_caches = False
        if add_remote_cache:
            self._artifacts.set_remotes([ArtifactCacheSpec(add_remote_cache, push=True)])
            has_remote_caches = True
        if use_configured_remote_caches:
            for project in self.context.get_projects():
                artifact_caches = configured_remote_artifact_cache_specs(self.context, project)
                if artifact_caches:  # artifact_caches is a list of ArtifactCacheSpec instances
                    self._artifacts.set_remotes(artifact_caches, project=project)
                    has_remote_caches = True
        if has_remote_caches:
            self._initialize_remote_caches()

        # Work out what we're going track, if anything
        self._track_cross_junctions = track_cross_junctions
        if track_elements:
            self._track_elements = self._get_elements_to_track(track_elements, track_selection)

        # Now resolve the cache keys once tracking elements have been resolved
        self._resolve_cache_keys()

    # cleanup()
    #
    # Cleans up resources used by the Pipeline.
    #
    def cleanup(self):
        if self._loader:
            self._loader.cleanup()

        # Reset the element loader state
        Element._reset_load_state()

    # get_selection()
    #
    # Args:
    #    mode (PipelineSelection): The PipelineSelection mode
    #
    # Various commands define a --deps option to specify what elements to
    # use in the result, this function reports a list that is appropriate for
    # the selected option.
    #
    def get_selection(self, mode):

        elements = None
        if mode == PipelineSelection.NONE:
            elements = self.targets
        elif mode == PipelineSelection.PLAN:
            elements = list(self._plan())
        else:
            if mode == PipelineSelection.ALL:
                scope = Scope.ALL
            elif mode == PipelineSelection.BUILD:
                scope = Scope.BUILD
            elif mode == PipelineSelection.RUN:
                scope = Scope.RUN

            elements = list(self.dependencies(scope))

        return self.remove_elements(elements)

    # dependencies()
    #
    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    # Args:
    #    scope (Scope): The scope to iterate over
    #    recurse (bool): Whether to recurse into dependencies
    #    include_sources (bool): Whether to include element sources in iteration
    #
    def dependencies(self, scope, *, recurse=True, include_sources=False):
        # Keep track of 'visited' in this scope, so that all targets
        # share the same context.
        visited = {}

        for target in self.targets:
            for element in target.dependencies(scope, recurse=recurse, visited=visited):
                if include_sources:
                    for source in element.sources():
                        yield source
                yield element

    #############################################################
    #                         Commands                          #
    #############################################################

    # remove_elements():
    #
    # Internal function
    #
    # Return what we are left with after the intersection between
    # excepted and target elements and their unique dependencies is
    # gone.
    #
    # Args:
    #    elements (list of elements): The list to remove elements from.
    def remove_elements(self, elements):
        targeted = list(self.dependencies(Scope.ALL))

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
        intersection = list(itertools.chain.from_iterable(
            find_intersection(element) for element in self._exceptions
        ))

        # Now use this set of elements to traverse the targeted
        # elements, except 'intersection' elements and their unique
        # dependencies.
        queue = []
        visited = []

        queue.extend(self.targets)
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

    #############################################################
    #                     Private Methods                       #
    #############################################################

    # _get_elements_to_track():
    #
    # Work out which elements are going to be tracked.
    #
    # Currently the 'mode' parameter only accepts
    # PipelineSelection.NONE or PipelineSelection.ALL
    #
    # This makes the assumption that the except elements are
    # meant to be removed from tracking element lists.
    #
    # Args:
    #    track_targets (list of str): List of target names
    #    mode (PipelineSelection): The PipelineSelection mode
    #
    # Returns:
    #    (list): List of Element objects to track
    #
    def _get_elements_to_track(self, track_targets, mode=PipelineSelection.ALL):
        planner = _Planner()

        # Convert target names to elements
        track_elements = [e for e in self.dependencies(Scope.ALL)
                          if e.name in track_targets]

        if mode != PipelineSelection.NONE:
            assert mode == PipelineSelection.ALL

            # Plan them out
            track_elements = planner.plan(track_elements, ignore_cache=True)

            # Filter out --except elements
            track_elements = self.remove_elements(track_elements)

        # Filter out cross junctioned elements
        if self._track_cross_junctions:
            self._assert_junction_tracking(track_elements)
        else:
            track_elements = self._filter_cross_junctions(track_elements)

        return track_elements

    # _prefilght()
    #
    # Preflights all the plugins in the pipeline
    #
    def _preflight(self):
        for element in self.dependencies(Scope.ALL):
            element._preflight()

    # _initialize_remote_caches()
    #
    # Initialize remote artifact caches, checking what
    # artifacts are contained by the artifact cache remotes
    #
    def _initialize_remote_caches(self):
        def remote_failed(url, error):
            self._message(MessageType.WARN, "Failed to fetch remote refs from {}: {}".format(url, error))

        with self.context.timed_activity("Initializing remote caches", silent_nested=True):
            self._artifacts.initialize_remotes(on_failure=remote_failed)

    # _resolve_cache_keys()
    #
    # Initially resolve the cache keys
    #
    def _resolve_cache_keys(self):
        track_elements = set(self._track_elements)

        with self.context.timed_activity("Resolving cached state", silent_nested=True):
            for element in self.dependencies(Scope.ALL):
                if element in track_elements:
                    # Load the pipeline in an explicitly inconsistent state, use
                    # this for pipelines with tracking queues enabled.
                    element._schedule_tracking()

                # Determine initial element state. This may resolve cache keys
                # and interrogate the artifact cache.
                element._update_state()

    # _assert_consistent()
    #
    # Asserts that the pipeline is in a consistent state, that
    # is to say that all sources are consistent and can at least
    # be fetched.
    #
    # Consequently it also means that cache keys can be resolved.
    #
    def _assert_consistent(self, toplevel):
        inconsistent = []
        with self.context.timed_activity("Checking sources"):
            for element in toplevel:
                if element._get_consistency() == Consistency.INCONSISTENT:
                    inconsistent.append(element)

        if inconsistent:
            detail = "Exact versions are missing for the following elements\n" + \
                     "Try tracking these elements first with `bst track`\n\n"
            for element in inconsistent:
                detail += "  " + element._get_full_name() + "\n"
            raise PipelineError("Inconsistent pipeline", detail=detail, reason="inconsistent-pipeline")

    # _filter_cross_junction()
    #
    # Filters out cross junction elements from the elements
    #
    # Args:
    #    elements (list of Element): The list of elements to be tracked
    #
    # Returns:
    #    (list): A filtered list of `elements` which does
    #            not contain any cross junction elements.
    #
    def _filter_cross_junctions(self, elements):
        return [
            element for element in elements
            if element._get_project() is self.project
        ]

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
        if self.project.ref_storage == ProjectRefStorage.PROJECT_REFS:
            return

        # Ideally, we would want to report every cross junction element but not
        # their dependencies, unless those cross junction elements dependencies
        # were also explicitly requested on the command line.
        #
        # But this is too hard, lets shoot for a simple error.
        for element in elements:
            element_project = element._get_project()
            if element_project is not self.project:
                detail = "Requested to track sources across junction boundaries\n" + \
                         "in a project which does not use project.refs ref-storage."

                raise PipelineError("Untrackable sources", detail=detail, reason="untrackable-sources")

    # _plan()
    #
    # Args:
    #    except_ (bool): Whether to filter out the except elements from the plan
    #
    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    def _plan(self, except_=True):
        build_plan = _Planner().plan(self.targets)

        if except_:
            build_plan = self.remove_elements(build_plan)

        for element in build_plan:
            yield element

    # _message()
    #
    # Local message propagator
    #
    def _message(self, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context.message(
            Message(None, message_type, message, **args))


# _Planner()
#
# An internal object used for constructing build plan
# from a given resolved toplevel element, while considering what
# parts need to be built depending on build only dependencies
# being cached, and depth sorting for more efficient processing.
#
class _Planner():
    def __init__(self):
        self.depth_map = {}
        self.visiting_elements = set()

    # Here we want to traverse the same element more than once when
    # it is reachable from multiple places, with the interest of finding
    # the deepest occurance of every element
    def plan_element(self, element, depth, ignore_cache):
        if element in self.visiting_elements:
            # circular dependency, already being processed
            return

        prev_depth = self.depth_map.get(element)
        if prev_depth is not None and prev_depth >= depth:
            # element and dependencies already processed at equal or greater depth
            return

        self.visiting_elements.add(element)
        for dep in element.dependencies(Scope.RUN, recurse=False):
            self.plan_element(dep, depth, ignore_cache)

        # Dont try to plan builds of elements that are cached already
        if ignore_cache or (not element._cached() and not element._remotely_cached()):
            for dep in element.dependencies(Scope.BUILD, recurse=False):
                self.plan_element(dep, depth + 1, ignore_cache)

        self.depth_map[element] = depth
        self.visiting_elements.remove(element)

    def plan(self, roots, ignore_cache=False):
        for root in roots:
            self.plan_element(root, 0, ignore_cache)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)
        return [item[0] for item in depth_sorted if ignore_cache or not item[0]._cached()]
