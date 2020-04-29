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

from buildstream import Element


# Element implementation for the 'stack' kind.
class StackElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # This plugin does not produce any artifacts when built
    BST_ELEMENT_HAS_ARTIFACT = False

    # This element does not allow sources
    BST_FORBID_SOURCES = True

    # Stack elements do not run any commands
    BST_RUN_COMMANDS = False

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
        vrootdir = sandbox.get_virtual_directory()
        vrootdir.descend("output", create=True)

        # And we're done
        return "/output"


# Plugin entry point
def setup():
    return StackElement
