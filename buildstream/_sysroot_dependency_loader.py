#
#  Copyright (C) 2019 Codethink Limited
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
#        Valentin David <valentin.david@codethink.co.uk>

import os
import itertools
from collections.abc import Mapping

from .dependency_loader import DependencyLoader, Dependency
from . import Element, ElementError, Scope, SandboxFlags


# SysrootDependencyLoader():
#
# `SysrootDependencyLoader` implements a `DependencyLoader` to extract
# sysroot'ed dependencies.
class SysrootDependencyLoader(DependencyLoader):

    def get_dependencies(self, node):
        sysroots = self.node_get_member(node, list, 'sysroots', default=[])
        dependencies = []

        for sysroot in sysroots:
            depends = self.node_get_member(sysroot, list, 'depends', default=[])
            build_depends = self.node_get_member(sysroot, list, 'build-depends', default=[])
            depends_iter = itertools.product(['all'], depends)
            build_depends_iter = itertools.product(['build'], build_depends)
            for default_type, dep in itertools.chain(depends_iter, build_depends_iter):
                if isinstance(dep, Mapping):
                    provenance = self.node_provenance(dep)
                    filename = self.node_get_member(node, str, 'filename')
                    dep_type = self.node_get_member(node, str, 'type', default=default_type)
                    junction = self.node_get_member(node, str, 'junction', default=None)
                    dependencies.append(Dependency(filename, dep_type=dep_type,
                                                   junction=junction, provenance=provenance))
                else:
                    provenance = self.node_provenance(sysroot)
                    dependencies.append(Dependency(dep, dep_type=default_type, provenance=provenance))

        return dependencies


# SysrootHelper():
#
# `SysrootHelper` should be used in element plugins that use
# `SysrootDependencyLoader` as dependency loader. It provides
# The implementation for staging.
class SysrootHelper:

    CONFIG_KEYS = ['sysroots']
    __layout = []

    def __init__(self, element, node):

        self.__element = element

        for sysroot in self.__element.node_get_member(node, list, 'sysroots', []):
            self.__element.node_validate(sysroot, ['path', 'depends', 'build-depends'])
            path = self.__element.node_subst_member(sysroot, 'path')
            depends = self.__element.node_get_member(sysroot, list, 'depends', default=[])
            build_depends = self.__element.node_get_member(sysroot, list, 'build-depends', default=[])
            for dep in itertools.chain(depends, build_depends):
                if isinstance(dep, Mapping):
                    self.__element.node_validate(dep, ['filename', 'type', 'junction'])
                    filename = self.__element.node_get_member(dep, str, 'filename')
                    junction = self.__element.node_get_member(dep, str, 'junction', default=None)
                else:
                    filename = dep
                    junction = None
                self.layout_add(filename, path, junction=junction)

    # layout_add():
    #
    # Adds a destination where a dependency should be staged
    #
    # Args:
    #    element (str): Element name of the dependency
    #    destination (str): Path where element will be staged
    #    junction (str): Junction of the dependency
    #
    # If `junction` is None, then the dependency should be in the same
    # project as the current element.
    #
    # If `junction` is ignored or `Element.IGNORE_JUNCTION`, the
    # junction of the dependency is not checked.  This is for backward
    # compliancy and should not be used.
    #
    # If `element` is None, the destination will just
    # be marked in the sandbox.
    def layout_add(self, element, destination, *, junction=Element.IGNORE_JUNCTION):
        #
        # Even if this is an empty list by default, make sure that its
        # instance data instead of appending stuff directly onto class data.
        #
        if not self.__layout:
            self.__layout = []
        item = {'element': element,
                'destination': destination}
        if junction is not Element.IGNORE_JUNCTION:
            item['junction'] = junction
        self.__layout.append(item)

    # validate():
    #
    # Verify that elements in layouts are dependencies.
    #
    # Raises:
    #    (ElementError): When a element is not in the dependencies
    #
    # This method is only useful when SysrootHelper.layout_add
    # has been called directly.
    #
    # This should be called in implementation of Plugin.preflight.
    def validate(self):
        if self.__layout:
            # Cannot proceed if layout specifies an element that isn't part
            # of the dependencies.
            for item in self.__layout:
                if not item['element']:
                    if not self.__search(item):
                        raise ElementError("{}: '{}' in layout not found in dependencies"
                                           .format(self.__element, item['element']))

    # stage():
    #
    # Stage dependencies and integrate root dependencies
    #
    # Args:
    #    stage_all (bool): Whether to stage all dependencies, not just the ones mapped
    #
    def stage(self, sandbox, stage_all):

        staged = set()
        sysroots = {}

        for item in self.__layout:

            # Skip layout members which dont stage an element
            if not item['element']:
                continue

            element = self.__search(item)
            staged.add(element)
            if item['destination'] not in sysroots:
                sysroots[item['destination']] = [element]
            else:
                sysroots[item['destination']].append(element)

        if stage_all or not self.__layout:
            for build_dep in self.__element.dependencies(Scope.BUILD, recurse=False):
                if build_dep in staged:
                    continue
                if '/' not in sysroots:
                    sysroots['/'] = [build_dep]
                else:
                    sysroots['/'].append(build_dep)

        for sysroot, deps in sysroots.items():
            with self.__element.timed_activity("Staging dependencies at {}".format(sysroot), silent_nested=True):
                if sysroot != '/':
                    virtual_dstdir = sandbox.get_virtual_directory()
                    virtual_dstdir.descend(sysroot.lstrip(os.sep).split(os.sep), create=True)
                all_deps = set()
                for dep in deps:
                    for run_dep in dep.dependencies(Scope.RUN):
                        all_deps.add(run_dep)
                self.__element.stage_dependency_artifacts(sandbox, Scope.BUILD, path=sysroot, dependencies=all_deps)

        with sandbox.batch(SandboxFlags.NONE):
            for item in self.__layout:

                # Skip layout members which dont stage an element
                if not item['element']:
                    continue

                element = self.__search(item)

                # Integration commands can only be run for elements staged to /
                if item['destination'] == '/':
                    with self.__element.timed_activity("Integrating {}".format(element.name),
                                                       silent_nested=True):
                        for dep in element.dependencies(Scope.RUN):
                            element.integrate(sandbox)

            if stage_all or not self.__layout:
                for build_dep in self.__element.dependencies(Scope.BUILD, recurse=False):
                    if build_dep in staged:
                        continue

                    with self.__element.timed_activity("Integrating {}".format(build_dep.name), silent_nested=True):
                        for dep in build_dep.dependencies(Scope.RUN):
                            dep.integrate(sandbox)

    # has_sysroots():
    #
    # Tells whether any element has been mapped
    #
    # Returns:
    #    (bool): Whether any element has been mapped
    def has_sysroots(self):
        return bool(self.__layout)

    # get_unique_key():
    #
    # Returns a value usable for an element unique key
    #
    # Returns:
    #    (dict): A dictionary that uniquely identify the mapping configuration
    def get_unique_key(self):
        return self.__layout

    # configure_sandbox():
    #
    # Configure the sandbox. Mark required directories in the sandbox.
    #
    # Args:
    #    extra_directories (list(str)): Extra directories to mark
    #
    # Because Sandbox.mark_directory should be called
    # only once, marked directories should passed as `extra_directories`
    # instead of being marked directly.
    def configure_sandbox(self, sandbox, extra_directories):

        directories = {directory: False for directory in extra_directories}

        for item in self.__layout:
            destination = item['destination']
            was_artifact = directories.get(destination, False)
            directories[destination] = item['element'] or was_artifact

        for directory, artifact in directories.items():
            # Root does not need to be marked as it is always mounted
            # with artifact (unless explicitly marked non-artifact)
            if directory != '/':
                sandbox.mark_directory(directory, artifact=artifact)

    #
    # Private methods
    #

    def __search(self, item):
        if 'junction' in item:
            return self.__element.search(Scope.BUILD, item['element'], junction=item['junction'])
        else:
            return self.__element.search(Scope.BUILD, item['element'])
