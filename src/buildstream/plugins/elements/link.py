#
#  Copyright (C) 2020 Codethink Limited
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
#        Tristan van Berkom <tristan.vanberkom@codethink.co.uk>

"""
link - Link elements
================================
This element is a link to another element, allowing one to create
a symbolic element which will be resolved to another element.


Overview
--------
The only configuration allowed in a ``link`` element is the specified
target :ref:`element name <format_element_names>` of the link.

.. code:: yaml

   kind: link

   config:
     target: element.bst

The ``link`` element can be used to refer to elements in subprojects, and
can be used to symbolically link :mod:`junction <elements.junction>` elements
as well as other elements.
"""

from buildstream import Element


# Element implementation for the 'link' kind.
class LinkElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # Links are not allowed any dependencies or sources
    BST_FORBID_BDEPENDS = True
    BST_FORBID_RDEPENDS = True
    BST_FORBID_SOURCES = True

    def configure(self, node):

        node.validate_keys(["target"])

        # Hold onto the provenance of the specified target,
        # allowing the loader to raise errors with better context.
        #
        target_node = node.get_scalar("target")
        self.target = target_node.as_str()
        self.target_provenance = target_node.get_provenance()

    def preflight(self):
        pass

    def get_unique_key(self):
        # This is only used early on but later discarded
        return 1

    def configure_sandbox(self, sandbox):
        assert False, "link elements should be discarded at load time"

    def stage(self, sandbox):
        assert False, "link elements should be discarded at load time"

    def generate_script(self):
        assert False, "link elements should be discarded at load time"

    def assemble(self, sandbox):
        assert False, "link elements should be discarded at load time"


# Plugin entry point
def setup():
    return LinkElement
