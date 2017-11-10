#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
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

"""Compose element

This element creates a selective composition of its dependencies.

This is normally used at near the end of a pipeline to prepare
something for later deployment.

Since this element's output includes its dependencies, it may only
depend on elements as `build` type dependencies.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../buildstream/plugins/elements/compose.yaml
     :language: yaml
"""

import os
from buildstream import utils
from buildstream import Element, ElementError, Scope


# Element implementation for the 'compose' kind.
class ComposeElement(Element):

    # The compose element's output is it's dependencies, so
    # we must rebuild if the dependencies change even when
    # not in strict build plans.
    #
    BST_STRICT_REBUILD = True

    def configure(self, node):
        self.node_validate(node, [
            'integrate', 'include', 'exclude', 'include-orphans'
        ])

        # We name this variable 'integration' only to avoid
        # collision with the Element.integrate() method.
        self.integration = self.node_get_member(node, bool, 'integrate')
        self.include = self.node_get_member(node, list, 'include')
        self.exclude = self.node_get_member(node, list, 'exclude')
        self.include_orphans = self.node_get_member(node, bool, 'include-orphans')

    def preflight(self):
        # Assert that the user did not list any runtime dependencies
        runtime_deps = list(self.dependencies(Scope.RUN, recurse=False))
        if runtime_deps:
            raise ElementError("{}: Only build type dependencies supported by compose elements"
                               .format(self))

        # Assert that the user did not specify any sources, as they will
        # be ignored by this element type anyway
        sources = list(self.sources())
        if sources:
            raise ElementError("{}: Compose elements may not have sources".format(self))

    def get_unique_key(self):
        key = {}
        key['integrate'] = self.integration,
        key['include'] = sorted(self.include),
        key['orphans'] = self.include_orphans

        if self.exclude:
            key['exclude'] = sorted(self.exclude)

        return key

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):

        # Stage deps in the sandbox root
        with self.timed_activity("Staging dependencies", silent_nested=True):
            self.stage_dependency_artifacts(sandbox, Scope.BUILD)

        # Make a snapshot of all the files.
        basedir = sandbox.get_directory()
        snapshot = {
            f: getmtime(os.path.join(basedir, f))
            for f in utils.list_relative_paths(basedir)
        }
        manifest = []
        integration_files = []

        # Run any integration commands provided by the dependencies
        # once they are all staged and ready
        if self.integration:
            with self.timed_activity("Integrating sandbox", silent_nested=True):
                for dep in self.dependencies(Scope.BUILD):
                    dep.integrate(sandbox)

                integration_files = [
                    path for path in utils.list_relative_paths(basedir)
                    if (snapshot.get(path) is None or
                        snapshot[path] != getmtime(os.path.join(basedir, path)))
                ]
                self.info("Integration effected {} files".format(len(integration_files)))

        manifest += integration_files

        # The remainder of this is expensive, make an early exit if
        # we're not being selective about what is to be included.
        if not (self.include or self.exclude) and self.include_orphans:
            return '/'

        # XXX We should be moving things outside of the build sandbox
        # instead of into a subdir. The element assemble() method should
        # support this in some way.
        #
        installdir = os.path.join(basedir, 'buildstream', 'install')
        stagedir = os.path.join(os.sep, 'buildstream', 'install')
        os.makedirs(installdir, exist_ok=True)

        # We already saved the manifest for created files in the integration phase,
        # now collect the rest of the manifest.
        #

        lines = []
        if self.include:
            lines.append("Including files from domains: " + ", ".join(self.include))
        else:
            lines.append("Including files from all domains")

        if self.exclude:
            lines.append("Excluding files from domains: " + ", ".join(self.exclude))

        if self.include_orphans:
            lines.append("Including orphaned files")
        else:
            lines.append("Excluding orphaned files")

        detail = "\n".join(lines)

        with self.timed_activity("Creating composition", detail=detail, silent_nested=True):
            self.stage_dependency_artifacts(sandbox, Scope.BUILD,
                                            path=stagedir,
                                            include=self.include,
                                            exclude=self.exclude,
                                            orphans=self.include_orphans)

            if self.integration:
                self.status("Moving {} integration files".format(len(integration_files)))
                utils.move_files(basedir, installdir, files=integration_files)

        # And we're done
        return os.path.join(os.sep, 'buildstream', 'install')


# Like os.path.getmtime(), but doesnt explode on symlinks
#
def getmtime(path):
    stat = os.lstat(path)
    return stat.st_mtime


# Plugin entry point
def setup():
    return ComposeElement
