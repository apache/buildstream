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

from . import _yaml


def node_items(node):
    """Iterate over a dictionary loaded from YAML

    Args:
       dict: The YAML loaded dictionary object

    Returns:
       list: List of key/value tuples to iterate over

    BuildStream holds some private data in dictionaries loaded from
    the YAML in order to preserve information to report in errors.

    This convenience function should be used instead of the dict.items()
    builtin function provided by python.
    """
    for key, value in node.items():
        if key == _yaml.PROVENANCE_KEY:
            continue
        yield (key, value)


def node_get_member(node, expected_type, member_name, default_value=None):
    """Fetch the value of a node member, raising an error if the value is
    missing or incorrectly typed.

    Args:
       node (dict): A dictionary loaded from YAML
       expected_type (type): The expected type of the node member
       member_name (str): The name of the member to fetch
       default_value (expected_type): A default value, for optional members

    Returns:
       The value of *member_name* in *node*, otherwise *default_value*

    Raises:
       :class:`.LoadError`

    **Example:**

    .. code:: python

      # Expect a string name in node
      name = node_get_member(node, str, 'name')

      # Fetch an optional integer
      level = node_get_member(node, int, 'level', -1)
    """
    return _yaml.node_get(node, expected_type, member_name, default_value=default_value)


def node_get_list_element(node, expected_type, member_name, indices):
    """Fetch the value of a list element from a node member, raising an error if the
    value is incorrectly typed.

    Args:
       node (dict): A dictionary loaded from YAML
       expected_type (type): The expected type of the node member
       member_name (str): The name of the member to fetch
       indices (list of int): List of indices to search, in case of nested lists

    Returns:
       The value of the list element in *member_name*, otherwise *default_value*

    Raises:
       :class:`.LoadError`

    **Example:**

    .. code:: python

      # Fetch the list itself
      things = node_get_member(node, list, 'things')

      # Iterate over the list indices
      for i in range(len(things)):

         # Fetch dict things
         thing = node_get_list_element(node, dict, 'things', [ i ])
    """
    _yaml.node_get(node, expected_type, member_name, indices=indices)
