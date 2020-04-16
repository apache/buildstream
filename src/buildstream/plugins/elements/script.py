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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""
script - Run scripts to create output
=====================================
This element allows one to run some commands to mutate the
input and create some output.

.. note::

   Script elements may only specify build dependencies. See
   :ref:`the format documentation <format_dependencies>` for more
   detail on specifying dependencies.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/script.yaml
     :language: yaml
"""

import buildstream


# Element implementation for the 'script' kind.
class ScriptElement(buildstream.ScriptElement):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        for n in node.get_sequence("layout", []):
            dst = n.get_str("destination")
            elm = n.get_str("element", None)
            self.layout_add(elm, dst)

        node.validate_keys(["commands", "root-read-only", "layout"])

        self.add_commands("commands", node.get_str_list("commands"))

        self.set_work_dir()
        self.set_install_root()
        self.set_root_read_only(node.get_bool("root-read-only", default=False))


# Plugin entry point
def setup():
    return ScriptElement
