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
stack - Symbolic Element for dependency grouping
================================================
Stack elements are simply a symbolic element used for representing
a logical group of elements.
"""

import os
from buildstream import Element


# Element implementation for the 'stack' kind.
class StackElement(Element):

    def configure(self, node):
        pass

    def preflight(self):
        pass

    def get_unique_key(self):
        # We do not add anything to the build, only our dependencies
        # do, so our unique key is just a constant.
        return 1

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):

        # Just create a dummy empty artifact, its existence is a statement
        # that all this stack's dependencies are built.
        rootdir = sandbox.get_directory()

        # XXX FIXME: This is currently needed because the artifact
        #            cache wont let us commit an empty artifact.
        #
        # We need to fix the artifact cache so that it stores
        # the actual artifact data in a subdirectory, then we
        # will be able to store some additional state in the
        # artifact cache, and we can also remove this hack.
        outputdir = os.path.join(rootdir, 'output', 'bst')

        # Ensure target directory parent
        os.makedirs(os.path.dirname(outputdir), exist_ok=True)

        # And we're done
        return '/output'


# Plugin entry point
def setup():
    return StackElement
