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
import datetime
from pluginbase import PluginBase
from operator import itemgetter

from ._message import Message, MessageType
from ._artifactcache import ArtifactCache
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory
from ._scheduler import Queue, SchedStatus
from .plugin import _plugin_lookup
from . import Element
from . import SourceError, ElementError, Consistency
from . import Scope
from . import _yaml


# Internal exception raised when a pipeline fails
#
class PipelineError(Exception):
    pass


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


# A queue which fetches element sources
#
class FetchQueue(Queue):

    def init(self):
        self.fetched_elements = []

    def process(self, element):
        for source in element.sources():
            source._fetch()

    def skip(self, element):
        return element._consistency() == Consistency.CACHED

    def done(self, element, result, returncode):

        if returncode != 0:
            return

        self.fetched_elements.append(element)
        for source in element.sources():

            # Successful fetch, we must be CACHED now
            source._bump_consistency(Consistency.CACHED)


# A queue which tracks sources
#
class TrackQueue(Queue):

    def init(self):
        self.changed_files = {}
        self.changed_sources = []

    def process(self, element):
        return element._track()

    def done(self, element, result, returncode):

        if returncode != 0:
            return

        # Set the new refs in the main process one by one as they complete
        for unique_id, new_ref in result:
            source = _plugin_lookup(unique_id)
            if source._set_ref(new_ref, source._Source__origin_node):

                # Successful update of ref, we're at least resolved now
                source._bump_consistency(Consistency.RESOLVED)
                self.changed_files[source._Source__origin_filename] = source._Source__origin_toplevel
                self.changed_sources.append(source)


# A queue which assembles elements
#
class AssembleQueue(Queue):

    def init(self):
        self.built_elements = []

    def process(self, element):
        element._assemble()
        return element._get_unique_id()

    def ready(self, element):
        return element._buildable()

    def skip(self, element):
        return element._cached()

    def done(self, element, result, returncode):
        # Elements are cached after they are successfully assembled
        if returncode == 0:
            element._set_cached()
            self.built_elements.append(element)


# Pipeline()
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    target (str): A bst filename relative to the project directory
#    target_variant (str): The selected variant of 'target', or None for the default
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
                 rewritable=False,
                 load_ticker=None,
                 resolve_ticker=None,
                 cache_ticker=None):
        self.context = context
        self.project = project
        self.artifacts = ArtifactCache(self.context)

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

        # Preflight right away, after constructing the tree
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            plugin.preflight()

        # Force interrogate the cache, ensure that elements have loaded
        # their consistency and cached states.
        for element in self.dependencies(Scope.ALL):
            if cache_ticker:
                cache_ticker(element.name)
            element._cached(recalculate=True)
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

        track = TrackQueue("Track", self.context.sched_fetchers)
        track.enqueue(dependencies)

        self.message(self.target, MessageType.START, "Starting track")
        starttime = datetime.datetime.now()
        status = scheduler.run([track])
        elapsed = datetime.datetime.now() - starttime
        changed = len(track.changed_files.items())

        def rewrite_changed_sources():
            for filename, toplevel in track.changed_files.items():
                fullname = os.path.join(self.project.directory, filename)
                _yaml.dump(toplevel, fullname)

        if status == SchedStatus.ERROR:
            self.message(self.target, MessageType.FAIL, "Track failed", elapsed=elapsed)
            raise PipelineError()
        elif status == SchedStatus.TERMINATED:
            rewrite_changed_sources()
            self.message(self.target, MessageType.WARN,
                         "Terminated after tracking {} sources".format(changed),
                         elapsed=elapsed)
            raise PipelineError()
        else:
            rewrite_changed_sources()
            self.message(self.target, MessageType.SUCCESS,
                         "Tracked {} sources".format(changed),
                         elapsed=elapsed)

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    scheduler (Scheduler): The scheduler to run this pipeline on
    #    needed (bool): If specified, track only sources that are
    #                   needed to build the artifacts of the pipeline
    #                   target. This does nothing when the pipeline
    #                   artifacts are already built.
    #
    def fetch(self, scheduler, needed):

        if needed:
            plan = list(Planner().plan(self.target))
        else:
            plan = list(self.dependencies(Scope.ALL))

        # Filter out elements with inconsistent sources, they can't be fetched.
        inconsistent = [elt for elt in plan if elt._consistency() == Consistency.INCONSISTENT]
        plan = [elt for elt in plan if elt not in inconsistent]

        # Filter out elements with cached sources, we already have them.
        cached = [elt for elt in plan if elt._consistency() == Consistency.CACHED]
        plan = [elt for elt in plan if elt not in cached]

        fetch = FetchQueue("Fetch", self.context.sched_fetchers)
        fetch.enqueue(plan)

        self.message(self.target, MessageType.START, "Fetching {} elements".format(len(plan)))
        starttime = datetime.datetime.now()
        status = scheduler.run([fetch])
        elapsed = datetime.datetime.now() - starttime
        fetched = len(fetch.fetched_elements)

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
    #
    def build(self, scheduler, build_all):

        if build_all:
            plan = self.dependencies(Scope.ALL)
        else:
            plan = Planner().plan(self.target)

        # We could bail out here on inconsistent elements, but
        # it could be the user wants to get as far as possible
        # even if some elements have failures.
        fetch = FetchQueue("Fetch", self.context.sched_fetchers)
        build = AssembleQueue("Build", self.context.sched_builders)
        fetch.enqueue(plan)

        self.message(self.target, MessageType.START, "Starting build")
        starttime = datetime.datetime.now()
        status = scheduler.run([fetch, build])
        elapsed = datetime.datetime.now() - starttime
        fetched = len(fetch.fetched_elements)
        built = len(build.built_elements)

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
