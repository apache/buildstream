#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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

import os
import shutil
from pluginbase import PluginBase
from operator import itemgetter

from .exceptions import _BstError
from ._message import Message, MessageType
from ._artifactcache import ArtifactCache
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory
from .plugin import _plugin_lookup
from . import Element
from . import SourceError, ElementError, Consistency
from . import Scope
from . import _yaml, utils

from ._scheduler import SchedStatus, TrackQueue, FetchQueue, BuildQueue


# Internal exception raised when a pipeline fails
#
class PipelineError(_BstError):

    def __init__(self, message=None):

        # The "Unclassified Error" should never appear to a user,
        # this only allows us to treat this internal error as
        # a _BstError from the frontend.
        if not message:
            message = "Unclassified Error"
        super(PipelineError, self).__init__(message)


class Planner():
    def __init__(self):
        self.depth_map = {}
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
        for dep in element._direct_deps(Scope.RUN):
            self.plan_element(dep, depth)

        # Dont try to plan builds of elements that are cached already
        if not element._cached():
            for dep in element._direct_deps(Scope.BUILD):
                self.plan_element(dep, depth + 1)

        self.depth_map[element] = depth
        self.visiting_elements.remove(element)

    def plan(self, root):
        self.plan_element(root, 0)

        depth_sorted = sorted(self.depth_map.items(), key=itemgetter(1), reverse=True)
        return [item[0] for item in depth_sorted if not item[0]._cached()]


# Pipeline()
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    target (str): A bst filename relative to the project directory
#    target_variant (str): The selected variant of 'target', or None for the default
#    inconsistent (bool): Whether to load the pipeline in a forcefully inconsistent state,
#                         this is appropriate when source tracking will run and the
#                         current source refs will not be the effective refs.
#    rewritable (bool): Whether the loaded files should be rewritable
#                       this is a bit more expensive due to deep copies
#    load_ticker (callable): A function which will be called for each loaded element
#    resolve_ticker (callable): A function which will be called for each resolved element
#    cache_ticker (callable): A function which will be called for each element
#                             while interrogating caches
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

    def __init__(self, context, project, target, target_variant,
                 inconsistent=False,
                 rewritable=False,
                 load_ticker=None,
                 resolve_ticker=None,
                 cache_ticker=None):
        self.context = context
        self.project = project
        self.artifacts = ArtifactCache(self.context)
        self.session_elements = 0
        self.total_elements = 0

        pluginbase = PluginBase(package='buildstream.plugins')
        self.element_factory = ElementFactory(pluginbase, project._plugin_element_paths)
        self.source_factory = SourceFactory(pluginbase, project._plugin_source_paths)

        loader = Loader(self.project.element_path, target, target_variant, context.arch)
        meta_element = loader.load(rewritable, load_ticker)
        if load_ticker:
            load_ticker(None)

        self.target = self.resolve(meta_element, ticker=resolve_ticker)
        if resolve_ticker:
            resolve_ticker(None)

        # Preflight directly after resolving elements, before ever interrogating
        # caches or anything.
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            plugin.preflight()

        self.total_elements = len(list(self.dependencies(Scope.ALL)))

        for element in self.dependencies(Scope.ALL):
            if cache_ticker:
                cache_ticker(element.name)

            if inconsistent:
                # Load the pipeline in an explicitly inconsistent state, use
                # this for pipelines with tracking queues enabled.
                element._force_inconsistent()
            else:
                # Resolve cache keys and interrogate the artifact cache
                # for the first time.
                element._cached()

        if cache_ticker:
            cache_ticker(None)

    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    def dependencies(self, scope, include_sources=False):
        for element in self.target.dependencies(scope):
            if include_sources:
                for source in element.sources():
                    yield source
            yield element

    # Generator function to iterate over only the elements
    # which are required to build the pipeline target, omitting
    # cached elements. The elements are yielded in a depth sorted
    # ordering for optimal build plans
    def plan(self):
        build_plan = Planner().plan(self.target)
        for element in build_plan:
            yield element

    # Local message propagator
    #
    def message(self, plugin, message_type, message, **kwargs):
        args = dict(kwargs)
        self.context._message(
            Message(plugin._get_unique_id(),
                    message_type,
                    message,
                    **args))

    # track()
    #
    # Trackes all the sources of all the elements in the pipeline,
    # i.e. all of the elements which the target somehow depends on.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    dependencies (list): List of elements to track
    #
    # If no error is encountered while tracking, then the project files
    # are rewritten inline.
    #
    def track(self, scheduler, dependencies):

        dependencies = list(dependencies)
        track = TrackQueue()
        track.enqueue(dependencies)
        self.session_elements = len(dependencies)

        self.message(self.target, MessageType.START, "Starting track")
        elapsed, status = scheduler.run([track])
        changed = len(track.changed_sources)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Track failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after tracking {} sources".format(changed),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
                         "Tracked {} sources".format(changed),
                         elapsed=elapsed)

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    dependencies (list): List of elements to fetch
    #
    def fetch(self, scheduler, dependencies):

        plan = dependencies

        # Filter out elements with inconsistent sources, they can't be fetched.
        inconsistent = [elt for elt in plan if elt._consistency() == Consistency.INCONSISTENT]
        plan = [elt for elt in plan if elt not in inconsistent]

        # Filter out elements with cached sources, we already have them.
        cached = [elt for elt in plan if elt._consistency() == Consistency.CACHED]
        plan = [elt for elt in plan if elt not in cached]

        self.session_elements = len(plan)
        fetch = FetchQueue()
        fetch.enqueue(plan)

        self.message(self.target, MessageType.START, "Fetching {} elements".format(len(plan)))
        elapsed, status = scheduler.run([fetch])
        fetched = len(fetch.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Fetch failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after fetching {} elements".format(fetched),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
                         "Fetched {} elements".format(fetched),
                         elapsed=elapsed)

    # Internal: Instantiates plugin-provided Element and Source instances
    # from MetaElement and MetaSource objects
    #
    def resolve(self, meta_element, resolved=None, ticker=None):
        if resolved is None:
            resolved = {}

        if meta_element in resolved:
            return resolved[meta_element]

        if ticker:
            ticker(meta_element.name)

        element = self.element_factory.create(meta_element.kind,
                                              self.context,
                                              self.project,
                                              self.artifacts,
                                              meta_element)

        resolved[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element._add_dependency(self.resolve(dep, resolved=resolved, ticker=ticker), Scope.RUN)
        for dep in meta_element.build_dependencies:
            element._add_dependency(self.resolve(dep, resolved=resolved, ticker=ticker), Scope.BUILD)

        # resolve sources
        for meta_source in meta_element.sources:
            element._add_source(
                self.source_factory.create(meta_source.kind,
                                           self.context,
                                           self.project,
                                           meta_source)
            )

        return element

    # build()
    #
    # Builds (assembles) elements in the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    build_all (bool): Whether to build all elements, or only those
    #                      which are required to build the target.
    #    track_first (bool): Track sources before fetching and building (implies build_all)
    #
    def build(self, scheduler, build_all, track_first):

        if build_all or track_first:
            plan = list(self.dependencies(Scope.ALL))
        else:
            plan = list(self.plan())

        # We could bail out here on inconsistent elements, but
        # it could be the user wants to get as far as possible
        # even if some elements have failures.
        fetch = FetchQueue()
        build = BuildQueue()
        track = None
        if track_first:
            track = TrackQueue()
            track.enqueue(plan)
            queues = [track, fetch, build]
        else:
            track = None
            fetch.enqueue(plan)
            queues = [fetch, build]

        self.session_elements = len(plan)

        self.message(self.target, MessageType.START, "Starting build")
        elapsed, status = scheduler.run(queues)
        fetched = len(fetch.processed_elements)
        built = len(build.processed_elements)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Build failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            self.message(self.target, MessageType.WARN,
                         "Terminated after fetching {} elements and building {} elements"
                         .format(fetched, built),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            self.message(self.target, MessageType.SUCCESS,
                         "Fetched {} elements and built {} elements".format(fetched, built),
                         elapsed=elapsed)

    # checkout()
    #
    # Checkout the pipeline target artifact to the specified directory
    #
    # Args:
    #    directory (str): The directory to checkout the artifact to
    #    force (bool): Force overwrite files which exist in `directory`
    #
    def checkout(self, directory, force):

        try:
            os.makedirs(directory, exist_ok=True)
        except e:
            raise PipelineError("Failed to create checkout directory: {}".format(e)) from e

        extract = self.artifacts.extract(self.target)
        if not force:
            extract_files = list(utils.list_relative_paths(extract))
            checkout_files = list(utils.list_relative_paths(directory))
            overwrites = [
                f for f in checkout_files
                if f in extract_files and f != '.'
            ]
            if overwrites:
                raise PipelineError("Files already exist in {}\n\n{}"
                                    .format(directory, "  " + "  \n".join(overwrites)))

        utils.link_files(extract, directory)

    # source_bundle()
    #
    # Create a build bundle for the given artifact.
    #
    # Args:
    #    directory (str): The directory to checkout the artifact to
    #
    def source_bundle(self, scheduler, directory):
        try:
            if not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
        except e:
            raise PipelineError("Failed to create output directory: {}".format(e)) from e

        dependencies = list(self.dependencies(Scope.ALL))

        self.fetch(scheduler, dependencies)

        # We don't use the scheduler for this as it is almost entirely IO
        # bound.

        source_directory = os.path.join(directory, 'source')
        os.makedirs(source_directory, exist_ok=True)

        from . import Sandbox
        sandbox = Sandbox(self.context, self.project, directory)
        for d in dependencies:
            if d.get_kind() == 'import':
                # We need to avoid the host tools binaries which come as part of
                # any BuildStream element's dependency chain. The whole reason for
                # bootstrapping is that no host tools binaries exist yet :-)
                pass
            else:
                element_source_directory = os.path.join(source_directory,
                                                        d.normal_name)
                try:
                    d.stage_sources(sandbox, path=element_source_directory)
                except:
                    self.message(self.target, MessageType.INFO,
                                 "Cleaning up partial directory '{}'"
                                 .format(element_source_directory))
                    shutil.rmtree(element_source_directory)
                    raise

