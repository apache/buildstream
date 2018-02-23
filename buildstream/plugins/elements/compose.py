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

import collections
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

        require_split = self.include or self.exclude or not self.include_orphans

        # Stage deps in the sandbox root
        with self.timed_activity("Staging dependencies", silent_nested=True):
            self.stage_dependency_artifacts(sandbox, Scope.BUILD)

        file_list = set()
        artifact_map = dict()
        if require_split:
            with self.timed_activity("Computing split", silent_nested=True):
                for dep in self.dependencies(Scope.BUILD):
                    manifest = dep.compute_manifest(include=self.include,
                                                 exclude=self.exclude,
                                                 orphans=self.include_orphans)
                    file_list.update(manifest.keys())
                    artifact_map.update(manifest)

        # Make a snapshot of all the files.
        basedir = sandbox.get_directory()
        snapshot = {
            f: getmtime(os.path.join(basedir, f))
            for f in utils.list_relative_paths(basedir)
        }

        modified_files = []
        removed_files = []
        added_files = []

        # Run any integration commands provided by the dependencies
        # once they are all staged and ready
        if self.integration:
            with self.timed_activity("Integrating sandbox"):
                for dep in self.dependencies(Scope.BUILD):
                    dep.integrate(sandbox)

                if require_split:

                    seen = set()
                    print("\n\n\nsnapshot: {}\n\n\n".format(snapshot))
                    # Calculate added modified files
                    for path in utils.list_relative_paths(basedir):
                        print("Got: {}".format(path))
                        seen.add(path)
                        if snapshot.get(path) is None:
                            added_files.append(path)
                        elif snapshot[path] != getmtime(os.path.join(basedir, path)):
                            modified_files.append(path)

                    # Calculate removed files
                    removed_files = [
                        path for path in file_list
                        if path not in seen
                    ]
                    self.info("Integration modified {}, added {} and removed {} files"
                              .format(len(modified_files), len(added_files), len(removed_files)))

        # The remainder of this is expensive, make an early exit if
        # we're not being selective about what is to be included.
        if not require_split:
            return '/'

        # Do we want to force include files which were modified by
        # the integration commands, even if they were not added ?
        #
        file_list.update(added_files)
        file_list.difference_update(removed_files)

        print("Explicitly removeD: {}".format(removed_files))

        # XXX We should be moving things outside of the build sandbox
        # instead of into a subdir. The element assemble() method should
        # support this in some way.
        #
        installdir = os.path.join(basedir, 'buildstream', 'install')
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

        total_files = len([f for f in file_list if f != '.'])

        with self.timed_activity("Creating composition", detail=detail, silent_nested=True):
            self.info("Composing {} files".format(total_files))
            utils.link_files(basedir, installdir, files=file_list)

        detail = self._readable_manifest(file_list, artifact_map)
        self.log("Composed {} files".format(total_files), detail=detail)

        # And we're done
        return os.path.join(os.sep, 'buildstream', 'install')

    # Show a list of files that made it into the artifact, grouped by the
    # artifact and split-rules domains that resulted in each one being there.
    def _readable_manifest(self, file_list, artifact_map):
        domains = collections.defaultdict(list)

        # Convert the filename->domain mapping into a domain->filename mapping.
        for filename in file_list:
            print("filename: {}, map: {}".format(filename, artifact_map.get(filename)))
            if filename == '.':
                continue

            if filename in artifact_map:
                entry = artifact_map[filename]
                domains_for_file = entry.get('domains') or ["(no domain)"]
                for domain in domains_for_file:
                    full_domain_name = entry['artifact'].name + " " + domain
                    if entry.get('integration', False) is True:
                        full_domain_name += " (modified during integration)"

                    domains[full_domain_name].append(filename)
            else:
                domains["Integration"].append(filename)

        # Display the mapping neatly for the user.
        lines = []
        for domain in sorted(domains):
            lines.extend(["", domain])

            contents = sorted(domains[domain])
            lines.extend("  - " + filename for filename in contents)

        return "\n".join(lines)


# Like os.path.getmtime(), but doesnt explode on symlinks
#
def getmtime(path):
    stat = os.lstat(path)
    return stat.st_mtime


# Plugin entry point
def setup():
    return ComposeElement
