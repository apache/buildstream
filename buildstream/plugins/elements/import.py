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

"""Import element

Import elements produce artifacts directly from its sources
without any kind of processing. These are typically used to
import an SDK to build on top of or to overlay your build with
some configuration data.

The empty configuration is as such:
  .. literalinclude:: ../../../buildstream/plugins/elements/import.yaml
     :language: yaml
"""

import os
import shutil
from buildstream import BuildElement


# Element implementation for the 'import' kind.
class ImportElement(BuildElement):

    def configure(self, node):
        self.source = self.node_subst_member(node, 'source')
        self.target = self.node_subst_member(node, 'target')

    def preflight(self):
        pass

    def get_unique_key(self):
        return {
            'source': self.source,
            'target': self.target
        }

    def assemble(self, sandbox):

        # Stage sources into the input directory
        self.stage_sources(sandbox, 'input')

        # XXX I think we'll have to make the sandbox directory public :-/
        rootdir = sandbox.executor.fs_root

        inputdir = os.path.join(rootdir, 'input')
        outputdir = os.path.join(rootdir, 'output')

        # The directory to grab
        inputdir = os.path.join(inputdir, self.source.lstrip(os.sep))
        inputdir = inputdir.rstrip(os.sep)

        # The output target directory
        outputdir = os.path.join(outputdir, self.target.lstrip(os.sep))
        outputdir = outputdir.rstrip(os.sep)

        # Ensure target directory parent
        os.makedirs(os.path.dirname(outputdir), exist_ok=True)

        # Move it over
        shutil.move(inputdir, outputdir)

        # And we're done
        return '/output'


# Plugin entry point
def setup():
    return ImportElement
