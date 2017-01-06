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

"""The BuildElement class is a convenience element one can derive from for
implementing the most common case of element.
"""

from collections import OrderedDict

from . import Element


_command_steps = ['bootstrap-commands',
                  'configure-commands',
                  'build-commands',
                  'test-commands',
                  'install-commands',
                  'strip-commands']
_command_prefixes = ['pre-', '', 'post-']


class BuildElement(Element):

    def configure(self, node):

        self.commands = {}

        for step in _command_steps:
            for prefix in _command_prefixes:
                command_name = prefix + step
                self.commands[command_name] = self._get_commands(node, command_name)

    def preflight(self):
        pass

    def get_unique_key(self):
        dictionary = OrderedDict()

        for command_name, command_list in self.commands.items():
            dictionary[command_name] = command_list

        return dictionary

    def _get_commands(self, node, name):
        list_node = self.node_get_member(node, list, name, default_value=[])
        commands = []

        for i in range(len(list_node)):
            command = self.node_subst_list_element(node, name, [i])
            commands.append(command)

        return commands
