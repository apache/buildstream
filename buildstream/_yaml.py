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

import collections
import copy
from enum import Enum

from ruamel import yaml
from . import LoadError, LoadErrorReason

# We store information in the loaded yaml on a DictProvenance
# stored in all dictionaries under this key
PROVENANCE_KEY = '__bst_provenance_info'


# Provenance tracks the origin of a given node in the parsed dictionary.
#
# Args:
#   node (dict, list, value): A binding to the originally parsed value
#   filename (string): The filename the node was loaded from
#   toplevel (dict): The toplevel of the loaded file, suitable for later dumps
#   line (int): The line number where node was parsed
#   col (int): The column number where node was parsed
#
class Provenance():
    def __init__(self, filename, node, toplevel, line=0, col=0):
        self.node = node
        self.filename = filename
        self.toplevel = toplevel
        self.line = line
        self.col = col

    # Convert a Provenance to a string for error reporting
    def __str__(self):
        return "%s [line %d column %d]" % (self.filename, self.line, self.col)


# A Provenance for dictionaries, these are stored in the copy of the
# loaded YAML tree and track the provenance of all members
#
class DictProvenance(Provenance):
    def __init__(self, filename, node, toplevel):
        super(DictProvenance, self).__init__(
            filename, node, toplevel,
            line=node.lc.line + 1, col=node.lc.col)

        self.members = {}


# A Provenance for dict members
#
class MemberProvenance(Provenance):
    def __init__(self, filename, parent_dict, member_name, toplevel):
        node = parent_dict[member_name]
        line, col = parent_dict.lc.value(member_name)
        super(MemberProvenance, self).__init__(
            filename, node, toplevel, line=line + 1, col=col)

        # Only used if member is a list
        elements = []


# A Provenance for list elements
#
class ElementProvenance(Provenance):
    def __init__(self, filename, parent_list, index, toplevel):
        node = parent_list[index]
        line, col = parent_list.lc.item(index)
        super(ElementProvenance, self).__init__(
            filename, node, toplevel, line=line + 1, col=col)

        # Only used if element is a list
        elements = []


# These exceptions are intended to be caught entirely within
# the BuildStream framework, hence they do not reside in the
# public exceptions.py
class CompositeError(Exception):
    def __init__(self, path, message):
        super(CompositeError, self).__init__(message)
        self.path = path


class CompositeOverrideError(CompositeError):
    def __init__(self, path):
        super(CompositeOverrideError, self).__init__(
            path,
            "Error compositing dictionary, not allowed to override key '%s'" %
            path)


class CompositeTypeError(CompositeError):
    def __init__(self, path, expected_type, actual_type):
        super(CompositeTypeError, self).__init__(
            path,
            "Error compositing dictionary key '%s', expected source type '%s' "
            "but received type '%s'" %
            (path, expected_type.__name__, actual_type.__name__))
        self.expected_type = expected_type
        self.actual_type = actual_type


# CompositePolicy
#
# An enumeration defining the behavior of the dictionary_composite()
# and dictionary_composite_inline() functions.
#
class CompositePolicy(Enum):

    # Every dict member overwrites members in the target dict
    OVERWRITE = 1

    # Arrays from the overriding dict are appended to arrays in the target dict
    ARRAY_APPEND = 2

    # Dictionary memebers may never replace existing members
    STRICT = 3


# Loads a dictionary from some YAML
#
# Args:
#    filename (str): The YAML file to load
#    shortname (str): The filename in shorthand for error reporting (or None)
#
# Returns (dict): A loaded copy of the YAML file with provenance information
#
# Raises: LoadError
#
def load(filename, shortname=None):

    try:
        with open(filename) as f:
            contents = yaml.load(f, yaml.loader.RoundTripLoader)
    except FileNotFoundError as e:
        raise LoadError(LoadErrorReason.MISSING_FILE,
                        "Could not find file at %s" % filename) from e
    except (yaml.scanner.ScannerError, yaml.composer.ComposerError) as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Malformed YAML:\n\n%s\n\n%s\n" % (e.problem, e.problem_mark)) from e

    if not isinstance(contents, dict):
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Loading YAML file did not specify a dictionary: %s" % filename)

    if not shortname:
        shortname = filename

    return node_decorated_copy(shortname, contents)


# node_decorated_copy()
#
# Create a copy of a loaded dict tree decorated with Provenance
# information, used directly after loading yaml
#
# Args:
#    filename (str): The filename
#    toplevel (node): The toplevel dictionary node
#
# Returns: A copy of the toplevel decorated with Provinance
#
def node_decorated_copy(filename, toplevel):
    result = copy.deepcopy(toplevel)

    node_decorate_dict(filename, result, toplevel, toplevel)

    return result


def node_decorate_dict(filename, target, source, toplevel):
    provenance = DictProvenance(filename, source, toplevel)
    target[PROVENANCE_KEY] = provenance

    for key, value in source.items():
        member = MemberProvenance(filename, source, key, toplevel)
        provenance.members[key] = member

        target_value = target.get(key)
        if isinstance(value, collections.Mapping):
            node_decorate_dict(filename, target_value, value, toplevel)
        elif isinstance(value, list):
            member.elements = node_decorate_list(filename, target_value, value, toplevel)


def node_decorate_list(filename, target, source, toplevel):

    elements = []

    for item in source:
        idx = source.index(item)
        target_item = target[idx]
        element = ElementProvenance(filename, source, idx, toplevel)

        if isinstance(item, collections.Mapping):
            node_decorate_dict(filename, target_item, item, toplevel)
        elif isinstance(item, list):
            element.elements = node_decorate_list(filename, target_item, item, toplevel)

        elements.append(element)

    return elements


# node_get_provenance()
#
# Gets the provenance for a node
#
# Args:
#   node (dict): a dictionary
#   key (str): key in the dictionary
#   indices (list of indexes): Index path, in the case of list values
#
# Returns: The Provenance of the dict, member or list element
#
def node_get_provenance(node, key=None, indices=[]):

    provenance = node.get(PROVENANCE_KEY)
    if key:
        provenance = provenance.members.get(key)
        for index in indices:
            provenance = provenance.elements[index]

    return provenance


# node_get()
#
# Fetches a value from a dictionary node and checks it for
# an expected value. Use default_value when parsing a value
# which is only optionally supplied.
#
# Args:
#    node (dict): The dictionary node
#    expected_type (type): The expected type for the value being searched
#    key (str): The key to get a value for in node
#    indices (list of ints): Optionally decend into lists of lists
#
# Returns:
#    The value if found in node, otherwise default_value is returned
#
# Raises:
#    LoadError, when the value found is not of the expected type
#
def node_get(node, expected_type, key, indices=[], default_value=None):
    value = node.get(key, default_value)
    provenance = node_get_provenance(node)
    if value is None:
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "%s: Dictionary did not contain expected key '%s'" % (str(provenance), key))

    provenance = node_get_provenance(node, key=key, indices=indices)
    path = key

    if indices:
        # Implied type check of the element itself
        value = node_get(node, list, key)
        for index in indices:
            value = value[index]
            path += '[%d]' % index

    if not isinstance(value, expected_type):
        # Attempt basic conversions if possible, typically we want to
        # be able to specify numeric values and convert them to strings,
        # but we dont want to try converting dicts/lists
        try:
            if not (expected_type == list or
                    expected_type == dict or
                    isinstance(value, list) or
                    isinstance(value, dict)):
                value = expected_type(value)
            else:
                raise ValueError()
        except ValueError:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "%s: Value of '%s' is not of the expected type '%s'" %
                            (str(provenance), path, expected_type.__name__))

    return value


# composite_dict():
#
# Composites values in target with values from source
#
# Args:
#    target (dict): A simple dictionary
#    source (dict): Another simple dictionary
#    policy (CompositePolicy): Defines compositing behavior
#    typesafe (bool): If True, then raise errors when overriding members
#                     with differing types
#
# Raises: CompositeError
#
# Unlike the dictionary update() method, nested values in source
# will not obsolete entire subdictionaries in target, instead both
# dictionaries will be recursed and a composition of both will result
#
# This is useful for overriding configuration files and element
# configurations.
#
def composite_dict(target, source, policy=CompositePolicy.OVERWRITE,
                   typesafe=False):
    source = copy.deepcopy(source)
    composite_dict_recurse(target, source, policy=policy, typesafe=typesafe)


def composite_dict_recurse(target, source, policy=CompositePolicy.OVERWRITE,
                           typesafe=False, path=None):
    target_provenance = target.get(PROVENANCE_KEY)
    source_provenance = source.get(PROVENANCE_KEY)

    for key, value in source.items():

        # Handle the provenance keys specially
        if key == PROVENANCE_KEY:
            continue

        # Track the full path of keys, only for raising CompositeError
        if path:
            thispath = path + '.' + key
        else:
            thispath = key

        target_value = target.get(key)

        if isinstance(value, collections.Mapping):

            # Handle creating new dicts on target side
            if target_value is None:
                target_value = {}
                target[key] = target_value

                # Give the new dict provenance
                value_provenance = value.get(PROVENANCE_KEY)
                if value_provenance:
                    target_value[PROVENANCE_KEY] = copy.deepcopy(value_provenance)

                # Add a new provenance member element to the containing dict
                target_provenance.members[key] = source_provenance.members[key]

            if not isinstance(target_value, collections.Mapping):
                raise CompositeTypeError(thispath, type(target_value), type(value))

            # Recurse into matching dictionary
            composite_dict_recurse(target_value, value, policy=policy, typesafe=typesafe, path=thispath)

        else:

            # Optionally enforce typesafe copy
            if (typesafe and
                target_value is not None and
                not isinstance(value, type(target_value))):
                raise CompositeTypeError(thispath, type(target_value), type(value))

            if policy == CompositePolicy.OVERWRITE:

                # Provenance and value is overwritten
                target_provenance.members[key] = source_provenance.members[key]
                target[key] = value

            elif policy == CompositePolicy.ARRAY_APPEND:

                if (isinstance(target_value, list) and
                    isinstance(value, list)):
                    target[key] += value

                    # Append element provenances from source list to target
                    target_list_provenance = target_provenance.members[key]
                    source_list_provenance = source_provenance.members[key]
                    for item in source_list_provenance.elements:
                        target_list_provenance.elements.append(item)
                else:
                    # Provenance is overwritten
                    target[key] = value
                    target_provenance.members[key] = source_provenance.members[key]

            elif policy == CompositePolicy.STRICT:

                if target_value is None:
                    target[key] = value
                    target_provenance.members[key] = source_provenance.members[key]
                else:
                    raise CompositeOverrideError(thispath)

            else:
                # Explicitly unhandled: Indicates a clear programming error
                raise Exception("Unhandled CompositePolicy in switch case")
