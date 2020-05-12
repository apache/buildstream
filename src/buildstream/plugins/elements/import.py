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
        inputdir = rootdir.descend("input")
        outputdir = rootdir.descend("output", create=True)

        # The directory to grab
        inputdir = inputdir.descend(*self.source.strip(os.sep).split(os.sep))

        # The output target directory
        outputdir = outputdir.descend(*self.target.strip(os.sep).split(os.sep), create=True)

        if inputdir.is_empty():
            raise ElementError("{}: No files were found inside directory '{}'".format(self, self.source))

        # Move it over
        outputdir.import_files(inputdir)

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
