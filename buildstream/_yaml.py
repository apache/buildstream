#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg LLP
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
#        Daniel Silverstone <daniel.silverstone@codethink.co.uk>
#        James Ennis <james.ennis@codethink.co.uk>

import sys
import string
from contextlib import ExitStack
from collections import OrderedDict, namedtuple
from collections.abc import Mapping, Sequence
from copy import deepcopy
from itertools import count

from ruamel import yaml
from ._exceptions import LoadError, LoadErrorReason


# Without this, pylint complains about all the `type(foo) is blah` checks
# because it feels isinstance() is more idiomatic.  Sadly, it is much slower to
# do `isinstance(foo, blah)` for reasons I am unable to fathom.  As such, we
# blanket disable the check for this module.
#
# pylint: disable=unidiomatic-typecheck


# Node()
#
# Container for YAML loaded data and its provenance
#
# All nodes returned (and all internal lists/strings) have this type (rather
# than a plain tuple, to distinguish them in things like node_sanitize)
#
# Members:
#   value (str/list/dict): The loaded value.
#   file_index (int): Index within _FILE_LIST (a list of loaded file paths).
#                     Negative indices indicate synthetic nodes so that
#                     they can be referenced.
#   line (int): The line number within the file where the value appears.
#   col (int): The column number within the file where the value appears.
#
# For efficiency, each field should be accessed by its integer index:
#   value = Node[0]
#   file_index = Node[1]
#   line = Node[2]
#   column = Node[3]
#
class Node(namedtuple('Node', ['value', 'file_index', 'line', 'column'])):
    def __contains__(self, what):
        assert False, \
            "BUG: Attempt to do `{} in {}` test".format(what, self)


# File name handling
_FILE_LIST = []


# Purely synthetic node will have None for the file number, have line number
# zero, and a negative column number which comes from inverting the next value
# out of this counter.  Synthetic nodes created with a reference node will
# have a file number from the reference node, some unknown line number, and
# a negative column number from this counter.
_SYNTHETIC_COUNTER = count(start=-1, step=-1)


# Returned from node_get_provenance
class ProvenanceInformation:

    __slots__ = (
        "filename",
        "shortname",
        "displayname",
        "line",
        "col",
        "toplevel",
        "node",
        "project",
        "is_synthetic",
    )

    def __init__(self, nodeish):
        self.node = nodeish
        if (nodeish is None) or (nodeish[1] is None):
            self.filename = ""
            self.shortname = ""
            self.displayname = ""
            self.line = 1
            self.col = 0
            self.toplevel = None
            self.project = None
        else:
            fileinfo = _FILE_LIST[nodeish[1]]
            self.filename = fileinfo[0]
            self.shortname = fileinfo[1]
            self.displayname = fileinfo[2]
            # We add 1 here to convert from computerish to humanish
            self.line = nodeish[2] + 1
            self.col = nodeish[3]
            self.toplevel = fileinfo[3]
            self.project = fileinfo[4]
        self.is_synthetic = (self.filename == '') or (self.col < 0)

    # Convert a Provenance to a string for error reporting
    def __str__(self):
        if self.is_synthetic:
            return "{} [synthetic node]".format(self.displayname)
        else:
            return "{} [line {:d} column {:d}]".format(self.displayname, self.line, self.col)


# These exceptions are intended to be caught entirely within
# the BuildStream framework, hence they do not reside in the
# public exceptions.py
class CompositeError(Exception):
    def __init__(self, path, message):
        super(CompositeError, self).__init__(message)
        self.path = path
        self.message = message


class YAMLLoadError(Exception):
    pass


# Representer for YAML events comprising input to the BuildStream format.
#
# All streams MUST represent a single document which must be a Mapping.
# Anything else is considered an error.
#
# Mappings must only have string keys, values are always represented as
# strings if they are scalar, or else as simple dictionaries and lists.
#
class Representer:
    __slots__ = (
        "_file_index",
        "state",
        "output",
        "keys",
    )

    # Initialise a new representer
    #
    # The file index is used to store into the Node instances so that the
    # provenance of the YAML can be tracked.
    #
    # Args:
    #   file_index (int): The index of this YAML file
    def __init__(self, file_index):
        self._file_index = file_index
        self.state = "init"
        self.output = []
        self.keys = []

    # Handle a YAML parse event
    #
    # Args:
    #   event (YAML Event): The event to be handled
    #
    # Raises:
    #   YAMLLoadError: Something went wrong.
    def handle_event(self, event):
        if getattr(event, "anchor", None) is not None:
            raise YAMLLoadError("Anchors are disallowed in BuildStream at line {} column {}"
                                .format(event.start_mark.line, event.start_mark.column))

        if event.__class__.__name__ == "ScalarEvent":
            if event.tag is not None:
                if not event.tag.startswith("tag:yaml.org,2002:"):
                    raise YAMLLoadError(
                        "Non-core tag expressed in input.  " +
                        "This is disallowed in BuildStream. At line {} column {}"
                        .format(event.start_mark.line, event.start_mark.column))

        handler = "_handle_{}_{}".format(self.state, event.__class__.__name__)
        handler = getattr(self, handler, None)
        if handler is None:
            raise YAMLLoadError(
                "Invalid input detected. No handler for {} in state {} at line {} column {}"
                .format(event, self.state, event.start_mark.line, event.start_mark.column))

        if handler is None:
            raise YAMLLoadError(
                "Invalid input detected. No handler for {} in state {} at line {} column {}"
                .format(event, self.state, event.start_mark.line, event.start_mark.column))

        self.state = handler(event)  # pylint: disable=not-callable

    # Get the output of the YAML parse
    #
    # Returns:
    #   (Node or None): Return the Node instance of the top level mapping or
    #                   None if there wasn't one.
    def get_output(self):
        try:
            return self.output[0]
        except IndexError:
            return None

    def _handle_init_StreamStartEvent(self, ev):
        return "stream"

    def _handle_stream_DocumentStartEvent(self, ev):
        return "doc"

    def _handle_doc_MappingStartEvent(self, ev):
        newmap = Node({}, self._file_index, ev.start_mark.line, ev.start_mark.column)
        self.output.append(newmap)
        return "wait_key"

    def _handle_wait_key_ScalarEvent(self, ev):
        self.keys.append(ev.value)
        return "wait_value"

    def _handle_wait_value_ScalarEvent(self, ev):
        key = self.keys.pop()
        self.output[-1][0][key] = \
            Node(ev.value, self._file_index, ev.start_mark.line, ev.start_mark.column)
        return "wait_key"

    def _handle_wait_value_MappingStartEvent(self, ev):
        new_state = self._handle_doc_MappingStartEvent(ev)
        key = self.keys.pop()
        self.output[-2][0][key] = self.output[-1]
        return new_state

    def _handle_wait_key_MappingEndEvent(self, ev):
        # We've finished a mapping, so pop it off the output stack
        # unless it's the last one in which case we leave it
        if len(self.output) > 1:
            self.output.pop()
            if type(self.output[-1][0]) is list:
                return "wait_list_item"
            else:
                return "wait_key"
        else:
            return "doc"

    def _handle_wait_value_SequenceStartEvent(self, ev):
        self.output.append(Node([], self._file_index, ev.start_mark.line, ev.start_mark.column))
        self.output[-2][0][self.keys[-1]] = self.output[-1]
        return "wait_list_item"

    def _handle_wait_list_item_SequenceStartEvent(self, ev):
        self.keys.append(len(self.output[-1][0]))
        self.output.append(Node([], self._file_index, ev.start_mark.line, ev.start_mark.column))
        self.output[-2][0].append(self.output[-1])
        return "wait_list_item"

    def _handle_wait_list_item_SequenceEndEvent(self, ev):
        # When ending a sequence, we need to pop a key because we retain the
        # key until the end so that if we need to mutate the underlying entry
        # we can.
        key = self.keys.pop()
        self.output.pop()
        if type(key) is int:
            return "wait_list_item"
        else:
            return "wait_key"

    def _handle_wait_list_item_ScalarEvent(self, ev):
        self.output[-1][0].append(
            Node(ev.value, self._file_index, ev.start_mark.line, ev.start_mark.column))
        return "wait_list_item"

    def _handle_wait_list_item_MappingStartEvent(self, ev):
        new_state = self._handle_doc_MappingStartEvent(ev)
        self.output[-2][0].append(self.output[-1])
        return new_state

    def _handle_doc_DocumentEndEvent(self, ev):
        if len(self.output) != 1:
            raise YAMLLoadError("Zero, or more than one document found in YAML stream")
        return "stream"

    def _handle_stream_StreamEndEvent(self, ev):
        return "init"


# Loads a dictionary from some YAML
#
# Args:
#    filename (str): The YAML file to load
#    shortname (str): The filename in shorthand for error reporting (or None)
#    copy_tree (bool): Whether to make a copy, preserving the original toplevels
#                      for later serialization
#    project (Project): The (optional) project to associate the parsed YAML with
#
# Returns (dict): A loaded copy of the YAML file with provenance information
#
# Raises: LoadError
#
def load(filename, shortname=None, copy_tree=False, *, project=None):
    if not shortname:
        shortname = filename

    if (project is not None) and (project.junction is not None):
        displayname = "{}:{}".format(project.junction.name, shortname)
    else:
        displayname = shortname

    file_number = len(_FILE_LIST)
    _FILE_LIST.append((filename, shortname, displayname, None, project))

    try:
        with open(filename) as f:
            contents = f.read()

        data = load_data(contents,
                         file_index=file_number,
                         file_name=filename,
                         copy_tree=copy_tree)

        return data
    except FileNotFoundError as e:
        raise LoadError(LoadErrorReason.MISSING_FILE,
                        "Could not find file at {}".format(filename)) from e
    except IsADirectoryError as e:
        raise LoadError(LoadErrorReason.LOADING_DIRECTORY,
                        "{} is a directory. bst command expects a .bst file."
                        .format(filename)) from e
    except LoadError as e:
        raise LoadError(e.reason, "{}: {}".format(displayname, e)) from e


# Like load(), but doesnt require the data to be in a file
#
def load_data(data, file_index=None, file_name=None, copy_tree=False):

    try:
        rep = Representer(file_index)
        for event in yaml.parse(data, Loader=yaml.CBaseLoader):
            rep.handle_event(event)
        contents = rep.get_output()
    except YAMLLoadError as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Malformed YAML:\n\n{}\n\n".format(e)) from e
    except Exception as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Severely malformed YAML:\n\n{}\n\n".format(e)) from e

    if not isinstance(contents, tuple) or not isinstance(contents[0], dict):
        # Special case allowance for None, when the loaded file has only comments in it.
        if contents is None:
            contents = Node({}, file_index, 0, 0)
        else:
            raise LoadError(LoadErrorReason.INVALID_YAML,
                            "YAML file has content of type '{}' instead of expected type 'dict': {}"
                            .format(type(contents[0]).__name__, file_name))

    # Store this away because we'll use it later for "top level" provenance
    if file_index is not None:
        _FILE_LIST[file_index] = (
            _FILE_LIST[file_index][0],  # Filename
            _FILE_LIST[file_index][1],  # Shortname
            _FILE_LIST[file_index][2],  # Displayname
            contents,
            _FILE_LIST[file_index][4],  # Project
        )

    if copy_tree:
        contents = node_copy(contents)
    return contents


# dump()
#
# Write a YAML node structure out to disk.
#
# This will always call `node_sanitize` on its input, so if you wanted
# to output something close to what you read in, consider using the
# `roundtrip_load` and `roundtrip_dump` function pair instead.
#
# Args:
#    contents (any): Content to write out
#    filename (str): The (optional) file name to write out to
def dump(contents, filename=None):
    roundtrip_dump(node_sanitize(contents), file=filename)


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
def node_get_provenance(node, key=None, indices=None):
    assert is_node(node)

    if key is None:
        # Retrieving the provenance for this node directly
        return ProvenanceInformation(node)

    if key and not indices:
        return ProvenanceInformation(node[0].get(key))

    nodeish = node[0].get(key)
    for idx in indices:
        nodeish = nodeish[0][idx]

    return ProvenanceInformation(nodeish)


# A sentinel to be used as a default argument for functions that need
# to distinguish between a kwarg set to None and an unset kwarg.
_sentinel = object()


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
#    default_value: Optionally return this value if the key is not found
#    allow_none: (bool): Allow None to be a valid value
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
def node_get(node, expected_type, key, indices=None, *, default_value=_sentinel, allow_none=False):
    assert type(node) is Node

    if indices is None:
        if default_value is _sentinel:
            value = node[0].get(key, Node(default_value, None, 0, 0))
        else:
            value = node[0].get(key, Node(default_value, None, 0, next(_SYNTHETIC_COUNTER)))

        if value[0] is _sentinel:
            provenance = node_get_provenance(node)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dictionary did not contain expected key '{}'".format(provenance, key))
    else:
        # Implied type check of the element itself
        # No need to synthesise useful node content as we destructure it immediately
        value = Node(node_get(node, list, key), None, 0, 0)
        for index in indices:
            value = value[0][index]
            if type(value) is not Node:
                value = (value,)

    # Optionally allow None as a valid value for any type
    if value[0] is None and (allow_none or default_value is None):
        return None

    if (expected_type is not None) and (not isinstance(value[0], expected_type)):
        # Attempt basic conversions if possible, typically we want to
        # be able to specify numeric values and convert them to strings,
        # but we dont want to try converting dicts/lists
        try:
            if (expected_type == bool and isinstance(value[0], str)):
                # Dont coerce booleans to string, this makes "False" strings evaluate to True
                # We don't structure into full nodes since there's no need.
                if value[0] in ('True', 'true'):
                    value = (True, None, 0, 0)
                elif value[0] in ('False', 'false'):
                    value = (False, None, 0, 0)
                else:
                    raise ValueError()
            elif not (expected_type == list or
                      expected_type == dict or
                      isinstance(value[0], (list, dict))):
                value = (expected_type(value[0]), None, 0, 0)
            else:
                raise ValueError()
        except (ValueError, TypeError):
            provenance = node_get_provenance(node, key=key, indices=indices)
            if indices:
                path = [key]
                path.extend("[{:d}]".format(i) for i in indices)
                path = "".join(path)
            else:
                path = key
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, expected_type.__name__))

    # Now collapse lists, and scalars, to their value, leaving nodes as-is
    if type(value[0]) is not dict:
        value = value[0]

    # Trim it at the bud, let all loaded strings from yaml be stripped of whitespace
    if type(value) is str:
        value = value.strip()

    elif type(value) is list:
        # Now we create a fresh list which unwraps the str and list types
        # semi-recursively.
        value = __trim_list_provenance(value)

    return value


def __trim_list_provenance(value):
    ret = []
    for entry in value:
        if type(entry) is not Node:
            entry = (entry, None, 0, 0)
        if type(entry[0]) is list:
            ret.append(__trim_list_provenance(entry[0]))
        elif type(entry[0]) is dict:
            ret.append(entry)
        else:
            ret.append(entry[0])
    return ret


# node_set()
#
# Set an item within the node.  If using `indices` be aware that the entry must
# already exist, or else a KeyError will be raised.  Use `node_extend_list` to
# create entries before using `node_set`
#
# Args:
#    node (tuple): The node
#    key (str): The key name
#    value: The value
#    indices: Any indices to index into the list referenced by key, like in
#             `node_get` (must be a list of integers)
#
def node_set(node, key, value, indices=None):
    if indices:
        node = node[0][key]
        key = indices.pop()
        for idx in indices:
            node = node[0][idx]
    if type(value) is Node:
        node[0][key] = value
    else:
        try:
            # Need to do this just in case we're modifying a list
            old_value = node[0][key]
        except KeyError:
            old_value = None
        if old_value is None:
            node[0][key] = Node(value, node[1], node[2], next(_SYNTHETIC_COUNTER))
        else:
            node[0][key] = Node(value, old_value[1], old_value[2], old_value[3])


# node_extend_list()
#
# Extend a list inside a node to a given length, using the passed
# default value to fill it out.
#
# Valid default values are:
#    Any string
#    An empty dict
#    An empty list
#
# Args:
#    node (node): The node
#    key (str): The list name in the node
#    length (int): The length to extend the list to
#    default (any): The default value to extend with.
def node_extend_list(node, key, length, default):
    assert type(default) is str or default in ([], {})

    list_node = node[0].get(key)
    if list_node is None:
        list_node = node[0][key] = Node([], node[1], node[2], next(_SYNTHETIC_COUNTER))

    assert type(list_node[0]) is list

    the_list = list_node[0]
    def_type = type(default)

    file_index = node[1]
    if the_list:
        line_num = the_list[-1][2]
    else:
        line_num = list_node[2]

    while length > len(the_list):
        if def_type is str:
            value = default
        elif def_type is list:
            value = []
        else:
            value = {}

        line_num += 1

        the_list.append(Node(value, file_index, line_num, next(_SYNTHETIC_COUNTER)))


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
    if type(node) is not Node:
        node = Node(node, None, 0, 0)
    for key, value in node[0].items():
        if type(value) is not Node:
            value = Node(value, None, 0, 0)
        if type(value[0]) is dict:
            yield (key, value)
        elif type(value[0]) is list:
            yield (key, __trim_list_provenance(value[0]))
        else:
            yield (key, value[0])


# node_keys()
#
# A convenience generator for iterating over loaded keys
# in a dictionary loaded from project YAML.
#
# Args:
#    node (dict): The dictionary node
#
# Yields:
#    (str): The key name
#
def node_keys(node):
    if type(node) is not Node:
        node = Node(node, None, 0, 0)
    yield from node[0].keys()


# node_del()
#
# A convenience generator for iterating over loaded key/value
# tuples in a dictionary loaded from project YAML.
#
# Args:
#    node (dict): The dictionary node
#    key (str): The key we want to remove
#    safe (bool): Whether to raise a KeyError if unable
#
def node_del(node, key, safe=False):
    try:
        del node[0][key]
    except KeyError:
        if not safe:
            raise


# is_node()
#
# A test method which returns whether or not the passed in value
# is a valid YAML node.  It is not valid to call this on a Node
# object which is not a Mapping.
#
# Args:
#    maybenode (any): The object to test for nodeness
#
# Returns:
#    (bool): Whether or not maybenode was a Node
#
def is_node(maybenode):
    # It's a programming error to give this a Node which isn't a mapping
    # so assert that.
    assert (type(maybenode) is not Node) or (type(maybenode[0]) is dict)
    # Now return the type check
    return type(maybenode) is Node


# new_synthetic_file()
#
# Create a new synthetic mapping node, with an associated file entry
# (in _FILE_LIST) such that later tracking can correctly determine which
# file needs writing to in order to persist the changes.
#
# Args:
#    filename (str): The name of the synthetic file to create
#    project (Project): The optional project to associate this synthetic file with
#
# Returns:
#    (Node): An empty YAML mapping node, whose provenance is to this new
#            synthetic file
#
def new_synthetic_file(filename, project=None):
    file_index = len(_FILE_LIST)
    node = Node({}, file_index, 0, 0)
    _FILE_LIST.append((filename,
                       filename,
                       "<synthetic {}>".format(filename),
                       node,
                       project))
    return node


# new_empty_node()
#
# Args:
#    ref_node (Node): Optional node whose provenance should be referenced
#
# Returns
#    (Node): A new empty YAML mapping node
#
def new_empty_node(ref_node=None):
    if ref_node is not None:
        return Node({}, ref_node[1], ref_node[2], next(_SYNTHETIC_COUNTER))
    else:
        return Node({}, None, 0, 0)


# new_node_from_dict()
#
# Args:
#   indict (dict): The input dictionary
#
# Returns:
#   (Node): A new synthetic YAML tree which represents this dictionary
#
def new_node_from_dict(indict):
    ret = {}
    for k, v in indict.items():
        vtype = type(v)
        if vtype is dict:
            ret[k] = new_node_from_dict(v)
        elif vtype is list:
            ret[k] = __new_node_from_list(v)
        else:
            ret[k] = Node(str(v), None, 0, next(_SYNTHETIC_COUNTER))
    return Node(ret, None, 0, next(_SYNTHETIC_COUNTER))


# Internal function to help new_node_from_dict() to handle lists
def __new_node_from_list(inlist):
    ret = []
    for v in inlist:
        vtype = type(v)
        if vtype is dict:
            ret.append(new_node_from_dict(v))
        elif vtype is list:
            ret.append(__new_node_from_list(v))
        else:
            ret.append(Node(str(v), None, 0, next(_SYNTHETIC_COUNTER)))
    return Node(ret, None, 0, next(_SYNTHETIC_COUNTER))


# node_contains()
#
# Args:
#    node (Node): The mapping node to query the contents of
#    entry (str): The key to look for in the mapping node
#
# Returns:
#    (bool): Whether entry is in the mapping in node.
#
def node_contains(node, entry):
    assert type(node) is Node
    return entry in node[0]


# _is_composite_list
#
# Checks if the given node is a Mapping with array composition
# directives.
#
# Args:
#    node (value): Any node
#
# Returns:
#    (bool): True if node was a Mapping containing only
#            list composition directives
#
# Raises:
#    (LoadError): If node was a mapping and contained a mix of
#                 list composition directives and other keys
#
def _is_composite_list(node):

    if type(node[0]) is dict:
        has_directives = False
        has_keys = False

        for key, _ in node_items(node):
            if key in ['(>)', '(<)', '(=)']:  # pylint: disable=simplifiable-if-statement
                has_directives = True
            else:
                has_keys = True

            if has_keys and has_directives:
                provenance = node_get_provenance(node)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Dictionary contains array composition directives and arbitrary keys"
                                .format(provenance))
        return has_directives

    return False


# _compose_composite_list()
#
# Composes a composite list (i.e. a dict with list composition directives)
# on top of a target list which is a composite list itself.
#
# Args:
#    target (Node): A composite list
#    source (Node): A composite list
#
def _compose_composite_list(target, source):
    clobber = source[0].get("(=)")
    prefix = source[0].get("(<)")
    suffix = source[0].get("(>)")
    if clobber is not None:
        # We want to clobber the target list
        # which basically means replacing the target list
        # with ourselves
        target[0]["(=)"] = clobber
        if prefix is not None:
            target[0]["(<)"] = prefix
        elif "(<)" in target[0]:
            target[0]["(<)"][0].clear()
        if suffix is not None:
            target[0]["(>)"] = suffix
        elif "(>)" in target[0]:
            target[0]["(>)"][0].clear()
    else:
        # Not clobbering, so prefix the prefix and suffix the suffix
        if prefix is not None:
            if "(<)" in target[0]:
                for v in reversed(prefix[0]):
                    target[0]["(<)"][0].insert(0, v)
            else:
                target[0]["(<)"] = prefix
        if suffix is not None:
            if "(>)" in target[0]:
                target[0]["(>)"][0].extend(suffix[0])
            else:
                target[0]["(>)"] = suffix


# _compose_list()
#
# Compose a composite list (a dict with composition directives) on top of a
# simple list.
#
# Args:
#    target (Node): The target list to be composed into
#    source (Node): The composition list to be composed from
#
def _compose_list(target, source):
    clobber = source[0].get("(=)")
    prefix = source[0].get("(<)")
    suffix = source[0].get("(>)")
    if clobber is not None:
        target[0].clear()
        target[0].extend(clobber[0])
    if prefix is not None:
        for v in reversed(prefix[0]):
            target[0].insert(0, v)
    if suffix is not None:
        target[0].extend(suffix[0])


# composite_dict()
#
# Compose one mapping node onto another
#
# Args:
#    target (Node): The target to compose into
#    source (Node): The source to compose from
#    path   (list): The path to the current composition node
#
# Raises: CompositeError
#
def composite_dict(target, source, path=None):
    if path is None:
        path = []
    for k, v in source[0].items():
        path.append(k)
        if type(v[0]) is list:
            # List clobbers anything list-like
            target_value = target[0].get(k)
            if not (target_value is None or
                    type(target_value[0]) is list or
                    _is_composite_list(target_value)):
                raise CompositeError(path,
                                     "{}: List cannot overwrite {} at: {}"
                                     .format(node_get_provenance(source, k),
                                             k,
                                             node_get_provenance(target, k)))
            # Looks good, clobber it
            target[0][k] = v
        elif _is_composite_list(v):
            if k not in target[0]:
                # Composite list clobbers empty space
                target[0][k] = v
            elif type(target[0][k][0]) is list:
                # Composite list composes into a list
                _compose_list(target[0][k], v)
            elif _is_composite_list(target[0][k]):
                # Composite list merges into composite list
                _compose_composite_list(target[0][k], v)
            else:
                # Else composing on top of normal dict or a scalar, so raise...
                raise CompositeError(path,
                                     "{}: Cannot compose lists onto {}".format(
                                         node_get_provenance(v),
                                         node_get_provenance(target[0][k])))
        elif type(v[0]) is dict:
            # We're composing a dict into target now
            if k not in target[0]:
                # Target lacks a dict at that point, make a fresh one with
                # the same provenance as the incoming dict
                target[0][k] = Node({}, v[1], v[2], v[3])
            if type(target[0]) is not dict:
                raise CompositeError(path,
                                     "{}: Cannot compose dictionary onto {}".format(
                                         node_get_provenance(v),
                                         node_get_provenance(target[0][k])))
            composite_dict(target[0][k], v, path)
        else:
            target_value = target[0].get(k)
            if target_value is not None and type(target_value[0]) is not str:
                raise CompositeError(path,
                                     "{}: Cannot compose scalar on non-scalar at {}".format(
                                         node_get_provenance(v),
                                         node_get_provenance(target[0][k])))
            target[0][k] = v
        path.pop()


# Like composite_dict(), but raises an all purpose LoadError for convenience
#
def composite(target, source):
    assert type(source[0]) is dict
    assert type(target[0]) is dict

    try:
        composite_dict(target, source)
    except CompositeError as e:
        source_provenance = node_get_provenance(source)
        error_prefix = ""
        if source_provenance:
            error_prefix = "{}: ".format(source_provenance)
        raise LoadError(LoadErrorReason.ILLEGAL_COMPOSITE,
                        "{}Failure composing {}: {}"
                        .format(error_prefix,
                                e.path,
                                e.message)) from e


# Like composite(target, source), but where target overrides source instead.
#
def composite_and_move(target, source):
    composite(source, target)

    to_delete = [key for key in target[0].keys() if key not in source[0]]
    for key, value in source[0].items():
        target[0][key] = value
    for key in to_delete:
        del target[0][key]


# Types we can short-circuit in node_sanitize for speed.
__SANITIZE_SHORT_CIRCUIT_TYPES = (int, float, str, bool)


# node_sanitize()
#
# Returns an alphabetically ordered recursive copy
# of the source node with internal provenance information stripped.
#
# Only dicts are ordered, list elements are left in order.
#
def node_sanitize(node, *, dict_type=OrderedDict):
    node_type = type(node)

    # If we have an unwrappable node, unwrap it
    if node_type is Node:
        node = node[0]
        node_type = type(node)

    # Short-circuit None which occurs ca. twice per element
    if node is None:
        return node

    # Next short-circuit integers, floats, strings, booleans, and tuples
    if node_type in __SANITIZE_SHORT_CIRCUIT_TYPES:
        return node

    # Now short-circuit lists.
    elif node_type is list:
        return [node_sanitize(elt, dict_type=dict_type) for elt in node]

    # Finally dict, and other Mappings need special handling
    elif node_type is dict:
        result = dict_type()

        key_list = [key for key, _ in node.items()]
        for key in sorted(key_list):
            result[key] = node_sanitize(node[key], dict_type=dict_type)

        return result

    # Sometimes we're handed tuples and we can't be sure what they contain
    # so we have to sanitize into them
    elif node_type is tuple:
        return tuple((node_sanitize(v, dict_type=dict_type) for v in node))

    # Everything else just gets returned as-is.
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
    invalid = next((key for key in node[0] if key not in valid_keys), None)

    if invalid:
        provenance = node_get_provenance(node, key=invalid)
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "{}: Unexpected key: {}".format(provenance, invalid))


# Node copying
#
# Unfortunately we copy nodes a *lot* and `isinstance()` is super-slow when
# things from collections.abc get involved.  The result is the following
# intricate but substantially faster group of tuples and the use of `in`.
#
# If any of the {node,list}_copy routines raise a ValueError
# then it's likely additional types need adding to these tuples.


# These types just have their value copied
__QUICK_TYPES = (str, bool)

# These are the directives used to compose lists, we need this because it's
# slightly faster during the node_final_assertions checks
__NODE_ASSERT_COMPOSITION_DIRECTIVES = ('(>)', '(<)', '(=)')


# node_copy()
#
# Make a deep copy of the given YAML node, preserving provenance.
#
# Args:
#    source (Node): The YAML node to copy
#
# Returns:
#    (Node): A deep copy of source with provenance preserved.
#
def node_copy(source):
    copy = {}
    for key, value in source[0].items():
        value_type = type(value[0])
        if value_type is dict:
            copy[key] = node_copy(value)
        elif value_type is list:
            copy[key] = _list_copy(value)
        elif value_type in __QUICK_TYPES:
            copy[key] = value
        else:
            raise ValueError("Unable to be quick about node_copy of {}".format(value_type))

    return Node(copy, source[1], source[2], source[3])


# Internal function to help node_copy() but for lists.
def _list_copy(source):
    copy = []
    for item in source[0]:
        item_type = type(item[0])
        if item_type is dict:
            copy.append(node_copy(item))
        elif item_type is list:
            copy.append(_list_copy(item))
        elif item_type in __QUICK_TYPES:
            copy.append(item)
        else:
            raise ValueError("Unable to be quick about list_copy of {}".format(item_type))

    return Node(copy, source[1], source[2], source[3])


# node_final_assertions()
#
# This must be called on a fully loaded and composited node,
# after all composition has completed.
#
# Args:
#    node (Mapping): The final composited node
#
# Raises:
#    (LoadError): If any assertions fail
#
def node_final_assertions(node):
    assert type(node) is Node

    for key, value in node[0].items():

        # Assert that list composition directives dont remain, this
        # indicates that the user intended to override a list which
        # never existed in the underlying data
        #
        if key in __NODE_ASSERT_COMPOSITION_DIRECTIVES:
            provenance = node_get_provenance(node, key)
            raise LoadError(LoadErrorReason.TRAILING_LIST_DIRECTIVE,
                            "{}: Attempt to override non-existing list".format(provenance))

        value_type = type(value[0])

        if value_type is dict:
            node_final_assertions(value)
        elif value_type is list:
            _list_final_assertions(value)


# Helper function for node_final_assertions(), but for lists.
def _list_final_assertions(values):
    for value in values[0]:
        value_type = type(value[0])

        if value_type is dict:
            node_final_assertions(value)
        elif value_type is list:
            _list_final_assertions(value)


# assert_symbol_name()
#
# A helper function to check if a loaded string is a valid symbol
# name and to raise a consistent LoadError if not. For strings which
# are required to be symbols.
#
# Args:
#    provenance (Provenance): The provenance of the loaded symbol, or None
#    symbol_name (str): The loaded symbol name
#    purpose (str): The purpose of the string, for an error message
#    allow_dashes (bool): Whether dashes are allowed for this symbol
#
# Raises:
#    LoadError: If the symbol_name is invalid
#
# Note that dashes are generally preferred for variable names and
# usage in YAML, but things such as option names which will be
# evaluated with jinja2 cannot use dashes.
def assert_symbol_name(provenance, symbol_name, purpose, *, allow_dashes=True):
    valid_chars = string.digits + string.ascii_letters + '_'
    if allow_dashes:
        valid_chars += '-'

    valid = True
    if not symbol_name:
        valid = False
    elif any(x not in valid_chars for x in symbol_name):
        valid = False
    elif symbol_name[0] in string.digits:
        valid = False

    if not valid:
        detail = "Symbol names must contain only alphanumeric characters, " + \
                 "may not start with a digit, and may contain underscores"
        if allow_dashes:
            detail += " or dashes"

        message = "Invalid symbol name for {}: '{}'".format(purpose, symbol_name)
        if provenance is not None:
            message = "{}: {}".format(provenance, message)

        raise LoadError(LoadErrorReason.INVALID_SYMBOL_NAME,
                        message, detail=detail)


# node_find_target()
#
# Searches the given node tree for the given target node.
#
# This is typically used when trying to walk a path to a given node
# for the purpose of then modifying a similar tree of objects elsewhere
#
# Args:
#    node (Node): The node at the root of the tree to search
#    target (Node): The node you are looking for in that tree
#
# Returns:
#    (list): A path from `node` to `target` or None if `target` is not in the subtree
def node_find_target(node, target):
    assert type(node) is Node
    assert type(target) is Node

    path = []
    if _walk_find_target(node, path, target):
        return path
    return None


# Helper for node_find_target() which walks a value
def _walk_find_target(node, path, target):
    if node[1:] == target[1:]:
        return True
    elif type(node[0]) is dict:
        return _walk_dict_node(node, path, target)
    elif type(node[0]) is list:
        return _walk_list_node(node, path, target)
    return False


# Helper for node_find_target() which walks a list
def _walk_list_node(node, path, target):
    for i, v in enumerate(node[0]):
        path.append(i)
        if _walk_find_target(v, path, target):
            return True
        del path[-1]
    return False


# Helper for node_find_target() which walks a mapping
def _walk_dict_node(node, path, target):
    for k, v in node[0].items():
        path.append(k)
        if _walk_find_target(v, path, target):
            return True
        del path[-1]
    return False


###############################################################################

# Roundtrip code

# Always represent things consistently:

yaml.RoundTripRepresenter.add_representer(OrderedDict,
                                          yaml.SafeRepresenter.represent_dict)

# Always parse things consistently

yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:int',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:float',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:bool',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:null',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:timestamp',
                                          yaml.RoundTripConstructor.construct_yaml_str)


# HardlineDumper
#
# This is a dumper used during roundtrip_dump which forces every scalar to be
# a plain string, in order to match the output format to the input format.
#
# If you discover something is broken, please add a test case to the roundtrip
# test in tests/internals/yaml/roundtrip-test.yaml
#
class HardlineDumper(yaml.RoundTripDumper):
    def __init__(self, *args, **kwargs):
        yaml.RoundTripDumper.__init__(self, *args, **kwargs)
        # For each of YAML 1.1 and 1.2, force everything to be a plain string
        for version in [(1, 1), (1, 2), None]:
            self.add_version_implicit_resolver(
                version,
                u'tag:yaml.org,2002:str',
                yaml.util.RegExp(r'.*'),
                None)


# roundtrip_load()
#
# Load a YAML file into memory in a form which allows roundtripping as best
# as ruamel permits.
#
# Note, the returned objects can be treated as Mappings and Lists and Strings
# but replacing content wholesale with plain dicts and lists may result
# in a loss of comments and formatting.
#
# Args:
#    filename (str): The file to load in
#    allow_missing (bool): Optionally set this to True to allow missing files
#
# Returns:
#    (Mapping): The loaded YAML mapping.
#
# Raises:
#    (LoadError): If the file is missing, or a directory, this is raised.
#                 Also if the YAML is malformed.
#
def roundtrip_load(filename, *, allow_missing=False):
    try:
        with open(filename, "r") as fh:
            data = fh.read()
        contents = roundtrip_load_data(data, filename=filename)
    except FileNotFoundError as e:
        if allow_missing:
            # Missing files are always empty dictionaries
            return {}
        else:
            raise LoadError(LoadErrorReason.MISSING_FILE,
                            "Could not find file at {}".format(filename)) from e
    except IsADirectoryError as e:
        raise LoadError(LoadErrorReason.LOADING_DIRECTORY,
                        "{} is a directory."
                        .format(filename)) from e
    return contents


# roundtrip_load_data()
#
# Parse the given contents as YAML, returning them as a roundtrippable data
# structure.
#
# A lack of content will be returned as an empty mapping.
#
# Args:
#    contents (str): The contents to be parsed as YAML
#    filename (str): Optional filename to be used in error reports
#
# Returns:
#    (Mapping): The loaded YAML mapping
#
# Raises:
#    (LoadError): Raised on invalid YAML, or YAML which parses to something other
#                 than a Mapping
#
def roundtrip_load_data(contents, *, filename=None):
    try:
        contents = yaml.load(contents, yaml.RoundTripLoader, preserve_quotes=True)
    except (yaml.scanner.ScannerError, yaml.composer.ComposerError, yaml.parser.ParserError) as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Malformed YAML:\n\n{}\n\n{}\n".format(e.problem, e.problem_mark)) from e

    # Special case empty files at this point
    if contents is None:
        # We'll make them empty mappings like the main Node loader
        contents = {}

    if not isinstance(contents, Mapping):
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "YAML file has content of type '{}' instead of expected type 'dict': {}"
                        .format(type(contents).__name__, filename))

    return contents


# roundtrip_dump()
#
# Dumps the given contents as a YAML file.  Ideally the contents came from
# parsing with `roundtrip_load` or `roundtrip_load_data` so that they will be
# dumped in the same form as they came from.
#
# If `file` is a string, it is the filename to write to, if `file` has a
# `write` method, it's treated as a stream, otherwise output is to stdout.
#
# Args:
#    contents (Mapping or list): The content to write out as YAML.
#    file (any): The file to write to
#
def roundtrip_dump(contents, file=None):
    assert type(contents) is not Node

    def stringify_dict(thing):
        for k, v in thing.items():
            if type(v) is str:
                pass
            elif isinstance(v, Mapping):
                stringify_dict(v)
            elif isinstance(v, Sequence):
                stringify_list(v)
            else:
                thing[k] = str(v)

    def stringify_list(thing):
        for i, v in enumerate(thing):
            if type(v) is str:
                pass
            elif isinstance(v, Mapping):
                stringify_dict(v)
            elif isinstance(v, Sequence):
                stringify_list(v)
            else:
                thing[i] = str(v)

    contents = deepcopy(contents)
    stringify_dict(contents)

    with ExitStack() as stack:
        if type(file) is str:
            from . import utils
            f = stack.enter_context(utils.save_file_atomic(file, 'w'))
        elif hasattr(file, 'write'):
            f = file
        else:
            f = sys.stdout
        yaml.round_trip_dump(contents, f, Dumper=HardlineDumper)
