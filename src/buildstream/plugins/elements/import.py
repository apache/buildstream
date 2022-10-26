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
import - Import sources directly
================================
Import elements produce artifacts directly from its sources
without any kind of processing. These are typically used to
import an SDK to build on top of or to overlay your build with
some configuration data.

The empty configuration is as such:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/import.yaml
     :language: yaml
"""

import os
from buildstream import Element, ElementError


# Element implementation for the 'import' kind.
class ImportElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # Import elements do not run any commands
    BST_RUN_COMMANDS = False

    def configure(self, node):
        node.validate_keys(["source", "target"])

        self.source = node.get_str("source")
        self.target = node.get_str("target")

    def preflight(self):
        # Assert that we have at least one source to fetch.

        sources = list(self.sources())
        if not sources:
            raise ElementError("{}: An import element must have at least one source.".format(self))

    def get_unique_key(self):
        return {"source": self.source, "target": self.target}

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):

        # Stage sources into the input directory
        self.stage_sources(sandbox, "input")

        rootdir = sandbox.get_virtual_directory()
        inputdir = rootdir.open_directory("input")
        outputdir = rootdir.open_directory("output", create=True)

        # The directory to grab
        inputdir = inputdir.open_directory(self.source.strip(os.sep))

        # The output target directory
        outputdir = outputdir.open_directory(self.target.strip(os.sep), create=True)

        if not inputdir:
            raise ElementError("{}: No files were found inside directory '{}'".format(self, self.source))

        # Move it over
        outputdir.import_files(inputdir, collect_result=False)

        # And we're done
        return "/output"

    def generate_script(self):
        build_root = self.get_variable("build-root")
        install_root = self.get_variable("install-root")
        commands = []

        # The directory to grab
        inputdir = os.path.join(build_root, self.normal_name, self.source.lstrip(os.sep))
        inputdir = inputdir.rstrip(os.sep)

        # The output target directory
        outputdir = os.path.join(install_root, self.target.lstrip(os.sep))
        outputdir = outputdir.rstrip(os.sep)

        # Ensure target directory parent exists but target directory doesn't
        commands.append("mkdir -p {}".format(os.path.dirname(outputdir)))
        commands.append("[ ! -e {outputdir} ] || rmdir {outputdir}".format(outputdir=outputdir))

        # Move it over
        commands.append("mv {} {}".format(inputdir, outputdir))

        script = ""
        for cmd in commands:
            script += "(set -ex; {}\n) || exit 1\n".format(cmd)

        return script


# Plugin entry point
def setup():
    return ImportElement
