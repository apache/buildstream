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

from pluginbase import PluginBase

from ._artifactcache import ArtifactCache
from ._elementfactory import ElementFactory
from ._loader import Loader
from ._sourcefactory import SourceFactory


# The Resolver class instantiates plugin-provided Element and Source classes
# from MetaElement and MetaSource objects
class Resolver():
    def __init__(self, context, project, element_factory, source_factory):
        self.context = context
        self.project = project
        self.element_factory = element_factory
        self.source_factory = source_factory
        self.resolved_elements = {}

    def resolve_element(self, meta_element):
        if meta_element in self.resolved_elements:
            return self.resolved_elements[meta_element]

        element = self.element_factory.create(meta_element.kind, self.context, self.project, meta_element)

        self.resolved_elements[meta_element] = element

        # resolve dependencies
        for dep in meta_element.dependencies:
            element.runtime_dependencies.append(self.resolve_element(dep))
        for dep in meta_element.build_dependencies:
            element.build_dependencies.append(self.resolve_element(dep))

        # resolve sources
        for meta_source in meta_element.sources:
            element.sources.append(self.resolve_source(meta_source))

        # XXX Preflighting should be postponed and only run on elements
        # which are in scope of what we're going to do
        element.preflight()

        return element

    def resolve_source(self, meta_source):
        source = self.source_factory.create(meta_source.kind, self.context, self.project, meta_source)

        # XXX Preflighting should be postponed and only run on elements
        # which are in scope of what we're going to do
        source.preflight()

        return source


class Pipeline():

    def __init__(self, context, project, target, target_variant):
        self.context = context
        self.project = project
        self.artifactcache = ArtifactCache(self.context)

        pluginbase = PluginBase(package='buildstream.plugins')
        self.element_factory = ElementFactory(pluginbase)
        self.source_factory = SourceFactory(pluginbase)

        loader = Loader(self.project.directory, target, target_variant, context.arch)
        meta_element = loader.load()

        resolver = Resolver(self.context, self.project, self.element_factory, self.source_factory)
        self.target = resolver.resolve_element(meta_element)
