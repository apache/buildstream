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

import sys
import collections
import copy
from enum import Enum
from contextlib import ExitStack

from ruamel import yaml
from ruamel.yaml.representer import SafeRepresenter, RoundTripRepresenter
from . import ImplError, LoadError, LoadErrorReason


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
        self.filename = filename
        self.node = node
        self.toplevel = toplevel
        self.line = line
        self.col = col

    # Convert a Provenance to a string for error reporting
    def __str__(self):
        return "%s [line %d column %d]" % (self.filename, self.line, self.col)

    # Abstract method
    def clone(self):
        raise ImplError("Unimplemented clone() in Provenance")


# A Provenance for dictionaries, these are stored in the copy of the
# loaded YAML tree and track the provenance of all members
#
class DictProvenance(Provenance):
    def __init__(self, filename, node, toplevel, line=None, col=None):

        if line is None or col is None:
            # Special case for loading an empty dict
            if hasattr(node, 'lc'):
                line = node.lc.line + 1
                col = node.lc.col
            else:
                line = 1
                col = 0

        super(DictProvenance, self).__init__(filename, node, toplevel, line=line, col=col)

        self.members = {}

    def clone(self):
        provenance = DictProvenance(self.filename, self.node, self.toplevel,
                                    line=self.line, col=self.col)

        provenance.members = {
            member_name: member.clone()
            for member_name, member in self.members.items()
        }
        return provenance


# A Provenance for dict members
#
class MemberProvenance(Provenance):
    def __init__(self, filename, parent_dict, member_name, toplevel,
                 node=None, line=None, col=None):

        if parent_dict is not None:
            node = parent_dict[member_name]
            line, col = parent_dict.lc.value(member_name)
            line += 1

        super(MemberProvenance, self).__init__(
            filename, node, toplevel, line=line, col=col)

        # Only used if member is a list
        self.elements = []

    def clone(self):
        provenance = MemberProvenance(self.filename, None, None, self.toplevel,
                                      node=self.node, line=self.line, col=self.col)
        provenance.elements = [e.clone() for e in self.elements]
        return provenance


# A Provenance for list elements
#
class ElementProvenance(Provenance):
    def __init__(self, filename, parent_list, index, toplevel,
                 node=None, line=None, col=None):

        if parent_list is not None:
            node = parent_list[index]
            line, col = parent_list.lc.item(index)
            line += 1

        super(ElementProvenance, self).__init__(
            filename, node, toplevel, line=line, col=col)

        # Only used if element is a list
        self.elements = []

    def clone(self):
        provenance = ElementProvenance(self.filename, None, None, self.toplevel,
                                       node=self.node, line=self.line, col=self.col)

        provenance.elements = [e.clone for e in self.elements]
        return provenance


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


# Loads a dictionary from some YAML
#
# Args:
#    filename (str): The YAML file to load
#    shortname (str): The filename in shorthand for error reporting (or None)
#    copy_tree (bool): Whether to make a copy, preserving the original toplevels
#                      for later serialization
#
# Returns (dict): A loaded copy of the YAML file with provenance information
#
# Raises: LoadError
#
def load(filename, shortname=None, copy_tree=False):
    if not shortname:
        shortname = filename

    try:
        with open(filename) as f:
            return load_data(f, shortname=shortname, copy_tree=copy_tree)
    except FileNotFoundError as e:
        raise LoadError(LoadErrorReason.MISSING_FILE,
                        "Could not find file at %s" % filename) from e


# Like load(), but doesnt require the data to be in a file
#
def load_data(data, shortname=None, copy_tree=False):

    try:
        contents = yaml.load(data, yaml.loader.RoundTripLoader)
    except (yaml.scanner.ScannerError, yaml.composer.ComposerError, yaml.parser.ParserError) as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Malformed YAML:\n\n%s\n\n%s\n" % (e.problem, e.problem_mark)) from e

    if not isinstance(contents, dict):
        # Special case allowance for None, when the loaded file has only comments in it.
        if contents is None:
            contents = {}
        else:
            raise LoadError(LoadErrorReason.INVALID_YAML,
                            "YAML file has content of type '%s' instead of expected type 'dict': %s" %
                            (type(contents).__name__, shortname))

    return node_decorated_copy(shortname, contents, copy_tree=copy_tree)


# Dumps a previously loaded YAML node to a file
#
# Args:
#    node (dict): A node previously loaded with _yaml.load() above
#    filename (str): The YAML file to load
#
def dump(node, filename=None):
    with ExitStack() as stack:
        if filename:
            f = stack.enter_context(open(filename, 'w'))
        else:
            f = sys.stdout
        yaml.round_trip_dump(node, f)


# node_decorated_copy()
#
# Create a copy of a loaded dict tree decorated with Provenance
# information, used directly after loading yaml
#
# Args:
#    filename (str): The filename
#    toplevel (node): The toplevel dictionary node
#    copy_tree (bool): Whether to load a copy and preserve the original
#
# Returns: A copy of the toplevel decorated with Provinance
#
def node_decorated_copy(filename, toplevel, copy_tree=False):
    if copy_tree:
        result = copy.deepcopy(toplevel)
    else:
        result = toplevel

    node_decorate_dict(filename, result, toplevel, toplevel)

    return result


def node_decorate_dict(filename, target, source, toplevel):
    provenance = DictProvenance(filename, source, toplevel)
    target[PROVENANCE_KEY] = provenance

    for key, value in node_items(source):
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
    if provenance and key:
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
# Note:
#    Returned strings are stripped of leading and trailing whitespace
#
def node_get(node, expected_type, key, indices=[], default_value=None):
    value = node.get(key, default_value)
    provenance = node_get_provenance(node)
    if value is None:
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "%s: Dictionary did not contain expected key '%s'" % (str(provenance), key))

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
            if (expected_type == bool and isinstance(value, str)):
                # Dont coerce booleans to string, this makes "False" strings evaluate to True
                if value == 'true' or value == 'True':
                    value = True
                elif value == 'false' or value == 'False':
                    value = False
                else:
                    raise ValueError()
            elif not (expected_type == list or
                      expected_type == dict or
                      isinstance(value, list) or
                      isinstance(value, dict)):
                value = expected_type(value)
            else:
                raise ValueError()
        except (ValueError, TypeError):
            provenance = node_get_provenance(node, key=key, indices=indices)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "%s: Value of '%s' is not of the expected type '%s'" %
                            (str(provenance), path, expected_type.__name__))

    # Trim it at the bud, let all loaded strings from yaml be stripped of whitespace
    if isinstance(value, str):
        value = value.strip()

    return value


# node_items()
#
# A convenience generator for iterating over loaded key/value
# tuples in a dictionary loaded from project YAML.
#
# Args:
#    node (dict): The dictionary node
#
# Yields:
#    (str): The key name
#    (anything): The value for the key
#
def node_items(node):
    for key, value in node.items():
        if key == PROVENANCE_KEY:
            continue
        yield (key, value)


# Gives a node a dummy provenance, in case of compositing dictionaries
# where the target is an empty {}
def ensure_provenance(node):
    provenance = node.get(PROVENANCE_KEY)
    if not provenance:
        provenance = DictProvenance('', node, node)
    node[PROVENANCE_KEY] = provenance

    return provenance


# is_ruamel_str():
#
# Args:
#    value: A value loaded from ruamel
#
# This returns if the value is "stringish", since ruamel
# has some complex types to represent strings, this is needed
# to avoid compositing exceptions in order to allow various
# string types to be interchangable and acceptable
#
def is_ruamel_str(value):

    if isinstance(value, str):
        return True
    elif isinstance(value, yaml.scalarstring.ScalarString):
        return True

    return False


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
def composite_dict(target, source, policy=CompositePolicy.OVERWRITE, typesafe=False, path=None):
    target_provenance = ensure_provenance(target)
    source_provenance = ensure_provenance(source)

    for key, source_value in node_items(source):

        # Track the full path of keys, only for raising CompositeError
        if path:
            thispath = path + '.' + key
        else:
            thispath = key

        target_value = target.get(key)

        if isinstance(source_value, collections.Mapping):

            # Handle creating new dicts on target side
            if target_value is None:
                target_value = {}
                target[key] = target_value

                # Give the new dict provenance
                value_provenance = source_value.get(PROVENANCE_KEY)
                if value_provenance:
                    target_value[PROVENANCE_KEY] = value_provenance.clone()

                # Add a new provenance member element to the containing dict
                target_provenance.members[key] = source_provenance.members[key]

            if not isinstance(target_value, collections.Mapping):
                raise CompositeTypeError(thispath, type(target_value), type(source_value))

            # Recurse into matching dictionary
            composite_dict(target_value, source_value, policy=policy, typesafe=typesafe, path=thispath)

        else:

            # Optionally enforce typesafe copy
            if typesafe and target_value is not None:

                # Exception here: depending on how strings were declared ruamel may
                # use a different type, but for our purposes, any stringish type will do.
                if not (is_ruamel_str(source_value) and is_ruamel_str(target_value)) \
                   and not isinstance(source_value, type(target_value)):
                    raise CompositeTypeError(thispath, type(target_value), type(source_value))

            if policy == CompositePolicy.OVERWRITE:

                # Provenance and value is overwritten
                target_provenance.members[key] = source_provenance.members[key]

                # Ensure target has only copies of mutable source values
                if (isinstance(target_value, list) and
                    isinstance(source_value, list)):
                    target[key] = list_chain_copy(source_value)
                else:
                    target[key] = source_value

            elif policy == CompositePolicy.ARRAY_APPEND:

                if (isinstance(target_value, list) and
                    isinstance(source_value, list)):

                    # Ensure target has only copies of mutable source values
                    target[key] += list_chain_copy(source_value)

                    # Append element provenances from source list to target
                    target_list_provenance = target_provenance.members[key]
                    source_list_provenance = source_provenance.members[key]
                    for item in source_list_provenance.elements:
                        target_list_provenance.elements.append(item.clone())
                else:
                    # Provenance is overwritten
                    target[key] = source_value
                    target_provenance.members[key] = source_provenance.members[key].clone()

            else:  # pragma: no cover
                raise ValueError("Unhandled CompositePolicy in switch case")


# Like composite_dict(), but raises an all purpose LoadError for convenience
#
def composite(target, source, policy=CompositePolicy.OVERWRITE, typesafe=False):
    provenance = node_get_provenance(source)
    try:
        composite_dict(target, source, policy=policy, typesafe=typesafe)
    except CompositeTypeError as e:
        error_prefix = ""
        if provenance:
            error_prefix = "[%s]: " % str(provenance)
        raise LoadError(LoadErrorReason.ILLEGAL_COMPOSITE,
                        "%sExpected '%s' type for configuration '%s', instead received '%s'" %
                        (error_prefix,
                         e.expected_type.__name__,
                         e.path,
                         e.actual_type.__name__)) from e


# SanitizedDict is an OrderedDict that is dumped as unordered mapping.
# This provides deterministic output for unordered mappings.
#
class SanitizedDict(collections.OrderedDict):
    pass


RoundTripRepresenter.add_representer(SanitizedDict,
                                     SafeRepresenter.represent_dict)


# node_sanitize()
#
# Returnes an alphabetically ordered recursive copy
# of the source node with internal provenance information stripped.
#
# Only dicts are ordered, list elements are left in order.
#
def node_sanitize(node):

    if isinstance(node, collections.Mapping):

        result = SanitizedDict()

        key_list = [key for key, _ in node_items(node)]
        for key in sorted(key_list):
            result[key] = node_sanitize(node[key])

        return result

    elif isinstance(node, list):
        return [node_sanitize(elt) for elt in node]

    return node


# node_validate()
#
# Validate the node so as to ensure the user has not specified
# any keys which are unrecognized by buildstream (usually this
# means a typo which would otherwise not trigger an error).
#
# Args:
#    node (dict): A dictionary loaded from YAML
#    valid_keys (list): A list of valid keys for the specified node
#
# Raises:
#    LoadError: In the case that the specified node contained
#               one or more invalid keys
#
def node_validate(node, valid_keys):

    # Probably the fastest way to do this: https://stackoverflow.com/a/23062482
    valid_keys = set(valid_keys)
    valid_keys.add(PROVENANCE_KEY)
    invalid = next((key for key in node if key not in valid_keys), None)

    if invalid:
        provenance = node_get_provenance(node, key=invalid)
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "[{}]: Unexpected key: {}".format(provenance, invalid))


def node_chain_copy(source):
    copy = collections.ChainMap({}, source)
    for key, value in source.items():
        if isinstance(value, collections.Mapping):
            copy[key] = node_chain_copy(value)
        elif isinstance(value, list):
            copy[key] = list_chain_copy(value)
        elif isinstance(value, Provenance):
            copy[key] = value.clone()

    return copy


def list_chain_copy(source):
    copy = []
    for item in source:
        if isinstance(item, collections.Mapping):
            copy.append(node_chain_copy(item))
        elif isinstance(item, list):
            copy.append(list_chain_copy(item))
        elif isinstance(item, Provenance):
            copy.append(item.clone())
        else:
            copy.append(item)

    return copy


def node_copy(source):
    copy = {}
    for key, value in source.items():
        if isinstance(value, collections.Mapping):
            copy[key] = node_copy(value)
        elif isinstance(value, list):
            copy[key] = list_copy(value)
        elif isinstance(value, Provenance):
            copy[key] = value.clone()
        else:
            copy[key] = value

    ensure_provenance(copy)

    return copy


def list_copy(source):
    copy = []
    for item in source:
        if isinstance(item, collections.Mapping):
            copy.append(node_copy(item))
        elif isinstance(item, list):
            copy.append(list_copy(item))
        elif isinstance(item, Provenance):
            copy.append(item.clone())
        else:
            copy.append(item)

    return copy
