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
from pluginbase import PluginBase
from operator import itemgetter

from ._artifactcache import ArtifactCache
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory
from ._scheduler import Scheduler, Queue
from . import SourceError, ElementError
from . import Scope
from . import _yaml

MAX_FETCHERS = 4
MAX_BUILDERS = 4


# The Resolver class instantiates plugin-provided Element and Source classes
# from MetaElement and MetaSource objects
class Resolver():
    def __init__(self, context, project, artifacts, element_factory, source_factory):
        self.context = context
        self.project = project
        self.element_factory = element_factory
        self.source_factory = source_factory
        self.resolved_elements = {}
        self.artifacts = artifacts

    def resolve_element(self, meta_element):
        if meta_element in self.resolved_elements:
            return self.resolved_elements[meta_element]

        element = self.element_factory.create(meta_element.kind,
                                              self.context,
                                              self.project,
                                              self.artifacts,
                                              meta_element)

        self.resolved_elements[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element._add_dependency(self.resolve_element(dep), Scope.RUN)

        for dep in meta_element.build_dependencies:
            element._add_dependency(self.resolve_element(dep), Scope.BUILD)

        # resolve sources
        for meta_source in meta_element.sources:
            element._add_source(self.resolve_source(meta_source))

        return element

    def resolve_source(self, meta_source):
        source = self.source_factory.create(meta_source.kind, self.context, self.project, meta_source)

        return source


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

    def process(self, element):
        try:
            # For remote artifact cache support
            # cachekey = element._get_cache_key()
            # if self.artifacts.fetch(self.project.name, element.name, cachekey):
            #     return
            for source in element._sources():
                source.fetch()
        except SourceError as e:
            print("ERROR: %s" % e)


# A queue which refreshes element sources
#
class RefreshQueue(Queue):

    def process(self, element):

        try:
            changed = element._refresh()
        except (SourceError, ElementError) as e:
            print("ERROR: %s" % e)

        return changed


# Pipeline()
#
# Args:
#    context (Context): The Context object
#    project (Project): The Project object
#    target (str): A bst filename relative to the project directory
#    target_variant (str): The selected variant of 'target', or None for the default
#
# Raises:
#    LoadError
#    PluginError
#    SourceError
#    ElementError
#    ProgramNotFoundError
#
class Pipeline():

    def __init__(self, context, project, target, target_variant):
        self.context = context
        self.project = project
        self.artifacts = ArtifactCache(self.context)

        pluginbase = PluginBase(package='buildstream.plugins')
        self.element_factory = ElementFactory(pluginbase, project._plugin_element_paths)
        self.source_factory = SourceFactory(pluginbase, project._plugin_source_paths)

        loader = Loader(self.project.directory, target, target_variant, context.arch)
        meta_element = loader.load()

        resolver = Resolver(context, project, self.artifacts, self.element_factory, self.source_factory)
        self.target = resolver.resolve_element(meta_element)

        # Preflight right away, after constructing the tree
        for plugin in self.dependencies(Scope.ALL, include_sources=True):
            plugin.preflight()

    # Generator function to iterate over elements and optionally
    # also iterate over sources.
    #
    def dependencies(self, scope, include_sources=False):
        for element in self.target.dependencies(scope):
            if include_sources:
                for source in element._sources():
                    yield source
            yield element

    # inconsistent()
    #
    # Reports a list of inconsistent sources.
    #
    # If a pipeline has inconsistent sources, it must
    # be refreshed before cache keys can be calculated
    # or anything else.
    #
    def inconsistent(self):
        sources = []
        for elt in self.dependencies(Scope.ALL):
            sources += elt._inconsistent()
        return sources

    # refresh()
    #
    # Refreshes all the sources of all the elements in the pipeline,
    # i.e. all of the elements which the target somehow depends on.
    #
    # Args:
    #    refresh_all (bool): Whether to refresh all sources, or only those
    #                        which are required for the current build plan
    #
    # Returns:
    #    (list): The Source objects which have changed due to the refresh
    #
    # If no error is encountered while refreshing, then the project files
    # are rewritten inline.
    #
    def refresh(self, refresh_all):
        refresh = RefreshQueue(MAX_FETCHERS)
        scheduler = Scheduler([refresh])

        if refresh_all:
            plan = self.dependencies(Scope.ALL)
        else:
            plan = Planner().plan(self.target)

        scheduler.run(plan)

        # If we were to parallelize the corner case of multiple
        # sources per element, then we would have to merge them
        # back here somehow, currently this works well because
        # the entire toplevel modified in the child process is
        # returned in one piece.
        #
        files = {}
        changed = []
        source_list = refresh.pop_result()
        while source_list is not None:
            for source in source_list:
                files[source._Source__origin_filename] = source._Source__origin_toplevel
                changed.append(source)
            source_list = refresh.pop_result()

        # Dump the files which changed
        for filename, toplevel in files.items():
            fullname = os.path.join(self.project.directory, filename)

            # print("Writing file: %s with value:\n%s" % (filename, toplevel))
            _yaml.dump(toplevel, fullname)

        return changed

    # fetch()
    #
    # Fetches sources on the pipeline.
    #
    # Args:
    #    fetch_all (bool): Whether to fetch all sources, or only those
    #                      which are required for the current build plan
    def fetch(self, fetch_all):
        fetch = FetchQueue(MAX_FETCHERS)
        scheduler = Scheduler([fetch])

        if fetch_all:
            plan = self.dependencies(Scope.ALL)
        else:
            plan = Planner().plan(self.target)

        # Filter out inconsistent elements
        plan = [elt for elt in plan if not elt._inconsistent()]

        scheduler.run(plan)

        # XXX Warn about remaining inconsistent elements
        # at this time
