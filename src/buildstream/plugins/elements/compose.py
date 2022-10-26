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

"""
compose - Compose the output of multiple elements
=================================================
This element creates a selective composition of its dependencies.

This is normally used at near the end of a pipeline to prepare
something for later deployment.

Since this element's output includes its dependencies, it may only
depend on elements as `build` type dependencies.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/compose.yaml
     :language: yaml
"""

import os
from buildstream import Element


# Element implementation for the 'compose' kind.
class ComposeElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # The compose element's output is its dependencies, so
    # we must rebuild if the dependencies change even when
    # not in strict build plans.
    #
    BST_STRICT_REBUILD = True

    # Compose artifacts must never have indirect dependencies,
    # so runtime dependencies are forbidden.
    BST_FORBID_RDEPENDS = True

    # This element ignores sources, so we should forbid them from being
    # added, to reduce the potential for confusion
    BST_FORBID_SOURCES = True

    def configure(self, node):
        node.validate_keys(["integrate", "include", "exclude", "include-orphans"])

        # We name this variable 'integration' only to avoid
        # collision with the Element.integrate() method.
        self.integration = node.get_bool("integrate")
        self.include = node.get_str_list("include")
        self.exclude = node.get_str_list("exclude")
        self.include_orphans = node.get_bool("include-orphans")

        # Inform the core that we will not need to run any commands in the sandbox
        if not self.integration:
            self.BST_RUN_COMMANDS = False

    def preflight(self):
        pass

    def get_unique_key(self):
        key = {"integrate": self.integration, "include": sorted(self.include), "orphans": self.include_orphans}

        if self.exclude:
            key["exclude"] = sorted(self.exclude)

        return key

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):

        # Stage deps in the sandbox root
        with self.timed_activity("Staging dependencies", silent_nested=True):
            self.stage_dependency_artifacts(sandbox)

    def assemble(self, sandbox):
        manifest = set()

        require_split = self.include or self.exclude or not self.include_orphans
        if require_split:
            with self.timed_activity("Computing split", silent_nested=True):
                for dep in self.dependencies():
                    files = dep.compute_manifest(
                        include=self.include, exclude=self.exclude, orphans=self.include_orphans
                    )
                    manifest.update(files)

        # Make a snapshot of all the files.
        vbasedir = sandbox.get_virtual_directory()
        removed_files = set()
        added_files = set()

        # Run any integration commands provided by the dependencies
        # once they are all staged and ready
        if self.integration:
            with self.timed_activity("Integrating sandbox"):
                if require_split:

                    # Make a snapshot of all the files before integration-commands are run.
                    snapshot = set(vbasedir.list_relative_paths())

                with sandbox.batch():
                    for dep in self.dependencies():
                        dep.integrate(sandbox)

                if require_split:
                    # Calculate added and removed files
                    post_integration_snapshot = vbasedir.list_relative_paths()
                    basedir_contents = set(post_integration_snapshot)
                    for path in manifest:
                        if path in snapshot and path not in basedir_contents:
                            removed_files.add(path)

                    for path in basedir_contents:
                        if path not in snapshot:
                            added_files.add(path)
                    self.info("Integration added {} and removed {} files".format(len(added_files), len(removed_files)))

        # The remainder of this is expensive, make an early exit if
        # we're not being selective about what is to be included.
        if not require_split:
            return "/"

        # Update the manifest with files which were added/removed by integration commands
        #
        manifest.update(added_files)
        manifest.difference_update(removed_files)

        # XXX We should be moving things outside of the build sandbox
        # instead of into a subdir. The element assemble() method should
        # support this in some way.
        #
        installdir = vbasedir.open_directory("buildstream/install", create=True)

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

        def import_filter(path):
            return path in manifest

        with self.timed_activity("Creating composition", detail=detail, silent_nested=True):
            self.info("Composing {} files".format(len(manifest)))
            installdir.import_files(vbasedir, filter_callback=import_filter, collect_result=False)

        # And we're done
        return os.path.join(os.sep, "buildstream", "install")


# Plugin entry point
def setup():
    return ComposeElement
