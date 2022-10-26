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

        # Hold onto the node, keep it around for provenance.
        #
        self.target_node = node.get_scalar("target")

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
