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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""Script element

This element allows one to run some commands to mutate the
input and create some output.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../buildstream/plugins/elements/script.yaml
     :language: yaml
"""

import buildstream


# Element implementation for the 'script' kind.
class ScriptElement(buildstream.ScriptElement):
    def configure(self, node):
        for n in self.node_get_member(node, list, 'layout', []):
            dst = self.node_subst_member(n, 'destination')
            elm = self.node_subst_member(n, 'element', default_value='') or None
            self.layout_add(elm, dst)

        cmds = []
        prefixes = ["pre-", "", "post-"]
        if "commands" not in node:
            raise ElementError("{}: Unexpectedly missing command group 'commands'"
                               .format(self))
        for prefix in prefixes:
            if prefix + "commands" in node:
                cmds += self.node_subst_list(node, prefix + "commands")
        self.add_commands("commands", cmds)

        self.set_work_dir()
        self.set_install_root()
        self.set_root_read_only(self.node_get_member(node, bool,
                                                     'root-read-only', False))


# Plugin entry point
def setup():
    return ScriptElement
