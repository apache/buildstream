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
#        Benjamin Schubert <bschubert@bloomberg.net>

import sys
import string
from contextlib import ExitStack
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from copy import deepcopy

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
cdef class Node:

    def __init__(self, object value, int file_index, int line, int column):
        self.value = value
        self.file_index = file_index
        self.line = line
        self.column = column

    def __contains__(self, what):
        # Delegate to the inner value, though this will likely not work
        # very well if the node is a list or string, it's unlikely that
        # code which has access to such nodes would do this.
        return what in self.value


# Metadata container for a yaml toplevel node.
#
# This class contains metadata around a yaml node in order to be able
# to trace back the provenance of a node to the file.
#
cdef class FileInfo:

    cdef str filename, shortname, displayname
    cdef Node toplevel,
    cdef object project

    def __init__(self, str filename, str shortname, str displayname, Node toplevel, object project):
        self.filename = filename
        self.shortname = shortname
        self.displayname = displayname
        self.toplevel = toplevel
        self.project = project


# File name handling
cdef _FILE_LIST = []


# Purely synthetic node will have _SYNTHETIC_FILE_INDEX for the file number, have line number
# zero, and a negative column number which comes from inverting the next value
# out of this counter.  Synthetic nodes created with a reference node will
# have a file number from the reference node, some unknown line number, and
# a negative column number from this counter.
cdef int _SYNTHETIC_FILE_INDEX = -1
cdef int __counter = 0

cdef int next_synthetic_counter():
    global __counter
    __counter -= 1
    return __counter


# Returned from node_get_provenance
cdef class ProvenanceInformation:

    def __init__(self, Node nodeish):
        cdef FileInfo fileinfo

        self.node = nodeish
        if (nodeish is None) or (nodeish.file_index is None):
            self.filename = ""
            self.shortname = ""
            self.displayname = ""
            self.line = 1
            self.col = 0
            self.toplevel = None
            self.project = None
        else:
            fileinfo = <FileInfo> _FILE_LIST[nodeish.file_index]
            self.filename = fileinfo.filename
            self.shortname = fileinfo.shortname
            self.displayname = fileinfo.displayname
            # We add 1 here to convert from computerish to humanish
            self.line = nodeish.line + 1
            self.col = nodeish.column
            self.toplevel = fileinfo.toplevel
            self.project = fileinfo.project
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


# Represents the various states in which the Representer can be
# while parsing yaml.
cdef enum RepresenterState:
    doc
    init
    stream
    wait_key
    wait_list_item
    wait_value


ctypedef RepresenterState (*representer_action)(Representer, object)

# Representer for YAML events comprising input to the BuildStream format.
#
# All streams MUST represent a single document which must be a Mapping.
# Anything else is considered an error.
#
# Mappings must only have string keys, values are always represented as
# strings if they are scalar, or else as simple dictionaries and lists.
#
cdef class Representer:

    cdef int _file_index
    cdef RepresenterState state
    cdef list output, keys

    # Initialise a new representer
    #
    # The file index is used to store into the Node instances so that the
    # provenance of the YAML can be tracked.
    #
    # Args:
    #   file_index (int): The index of this YAML file
    def __init__(self, int file_index):
        self._file_index = file_index
        self.state = RepresenterState.init
        self.output = []
        self.keys = []

    # Handle a YAML parse event
    #
    # Args:
    #   event (YAML Event): The event to be handled
    #
    # Raises:
    #   YAMLLoadError: Something went wrong.
    cdef void handle_event(self, event) except *:
        if getattr(event, "anchor", None) is not None:
            raise YAMLLoadError("Anchors are disallowed in BuildStream at line {} column {}"
                                .format(event.start_mark.line, event.start_mark.column))

        cdef str event_name = event.__class__.__name__

        if event_name == "ScalarEvent":
            if event.tag is not None:
                if not event.tag.startswith("tag:yaml.org,2002:"):
                    raise YAMLLoadError(
                        "Non-core tag expressed in input.  " +
                        "This is disallowed in BuildStream. At line {} column {}"
                        .format(event.start_mark.line, event.start_mark.column))

        cdef representer_action handler = self._get_handler_for_event(event_name)
        if not handler:
            raise YAMLLoadError(
                "Invalid input detected. No handler for {} in state {} at line {} column {}"
                .format(event, self.state, event.start_mark.line, event.start_mark.column))

        # Cython weirdness here, we need to pass self to the function
        self.state = <RepresenterState> handler(self, event)  # pylint: disable=not-callable

    # Get the output of the YAML parse
    #
    # Returns:
    #   (Node or None): Return the Node instance of the top level mapping or
    #                   None if there wasn't one.
    cdef Node get_output(self):
        if len(self.output):
            return self.output[0]
        return None

    cdef representer_action _get_handler_for_event(self, str event_name):
        if self.state == RepresenterState.wait_list_item:
            if event_name == "ScalarEvent":
                return self._handle_wait_list_item_ScalarEvent
            elif event_name == "MappingStartEvent":
                return self._handle_wait_list_item_MappingStartEvent
            elif event_name == "SequenceStartEvent":
                return self._handle_wait_list_item_SequenceStartEvent
            elif event_name == "SequenceEndEvent":
                return self._handle_wait_list_item_SequenceEndEvent
        elif self.state == RepresenterState.wait_value:
            if event_name == "ScalarEvent":
                return self._handle_wait_value_ScalarEvent
            elif event_name == "MappingStartEvent":
                return self._handle_wait_value_MappingStartEvent
            elif event_name == "SequenceStartEvent":
                return self._handle_wait_value_SequenceStartEvent
        elif self.state == RepresenterState.wait_key:
            if event_name == "ScalarEvent":
                return self._handle_wait_key_ScalarEvent
            elif event_name == "MappingEndEvent":
                return self._handle_wait_key_MappingEndEvent
        elif self.state == RepresenterState.stream:
            if event_name == "DocumentStartEvent":
                return self._handle_stream_DocumentStartEvent
            elif event_name == "StreamEndEvent":
                return self._handle_stream_StreamEndEvent
        elif self.state == RepresenterState.doc:
            if event_name == "MappingStartEvent":
                return self._handle_doc_MappingStartEvent
            elif event_name == "DocumentEndEvent":
                return self._handle_doc_DocumentEndEvent
        elif self.state == RepresenterState.init and event_name == "StreamStartEvent":
            return self._handle_init_StreamStartEvent
        return NULL

    cdef RepresenterState _handle_init_StreamStartEvent(self, object ev):
        return RepresenterState.stream

    cdef RepresenterState _handle_stream_DocumentStartEvent(self, object ev):
        return RepresenterState.doc

    cdef RepresenterState _handle_doc_MappingStartEvent(self, object ev):
        newmap = Node({}, self._file_index, ev.start_mark.line, ev.start_mark.column)
        self.output.append(newmap)
        return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_key_ScalarEvent(self, object ev):
        self.keys.append(ev.value)
        return RepresenterState.wait_value

    cdef RepresenterState _handle_wait_value_ScalarEvent(self, object ev):
        key = self.keys.pop()
        (<dict> (<Node> self.output[-1]).value)[key] = \
            Node(ev.value, self._file_index, ev.start_mark.line, ev.start_mark.column)
        return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_value_MappingStartEvent(self, object ev):
        cdef RepresenterState new_state = self._handle_doc_MappingStartEvent(ev)
        key = self.keys.pop()
        (<dict> (<Node> self.output[-2]).value)[key] = self.output[-1]
        return new_state

    cdef RepresenterState _handle_wait_key_MappingEndEvent(self, object ev):
        # We've finished a mapping, so pop it off the output stack
        # unless it's the last one in which case we leave it
        if len(self.output) > 1:
            self.output.pop()
            if type((<Node> self.output[-1]).value) is list:
                return RepresenterState.wait_list_item
            else:
                return RepresenterState.wait_key
        else:
            return RepresenterState.doc

    cdef RepresenterState _handle_wait_value_SequenceStartEvent(self, object ev):
        self.output.append(Node([], self._file_index, ev.start_mark.line, ev.start_mark.column))
        (<dict> (<Node> self.output[-2]).value)[self.keys[-1]] = self.output[-1]
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_SequenceStartEvent(self, object ev):
        self.keys.append(len((<Node> self.output[-1]).value))
        self.output.append(Node([], self._file_index, ev.start_mark.line, ev.start_mark.column))
        (<list> (<Node> self.output[-2]).value).append(self.output[-1])
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_SequenceEndEvent(self, object ev):
        # When ending a sequence, we need to pop a key because we retain the
        # key until the end so that if we need to mutate the underlying entry
        # we can.
        key = self.keys.pop()
        self.output.pop()
        if type(key) is int:
            return RepresenterState.wait_list_item
        else:
            return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_list_item_ScalarEvent(self, object ev):
        (<Node> self.output[-1]).value.append(
            Node(ev.value, self._file_index, ev.start_mark.line, ev.start_mark.column))
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_MappingStartEvent(self, object ev):
        cdef RepresenterState new_state = self._handle_doc_MappingStartEvent(ev)
        (<list> (<Node> self.output[-2]).value).append(self.output[-1])
        return new_state

    cdef RepresenterState _handle_doc_DocumentEndEvent(self, object ev):
        if len(self.output) != 1:
            raise YAMLLoadError("Zero, or more than one document found in YAML stream")
        return RepresenterState.stream

    cdef RepresenterState _handle_stream_StreamEndEvent(self, object ev):
        return RepresenterState.init


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
cpdef Node load(str filename, str shortname=None, bint copy_tree=False, object project=None):
    if not shortname:
        shortname = filename

    cdef str displayname
    if (project is not None) and (project.junction is not None):
        displayname = "{}:{}".format(project.junction.name, shortname)
    else:
        displayname = shortname

    cdef Py_ssize_t file_number = len(_FILE_LIST)
    _FILE_LIST.append(FileInfo(filename, shortname, displayname, None, project))

    cdef Node data

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
cpdef Node load_data(str data, int file_index=_SYNTHETIC_FILE_INDEX, str file_name=None, bint copy_tree=False):
    cdef Representer rep
    cdef FileInfo f_info

    try:
        rep = Representer(file_index)
        parser = yaml.CParser(data)

        try:
            while parser.check_event():
                rep.handle_event(parser.get_event())
        finally:
            parser.dispose()

        contents = rep.get_output()
    except YAMLLoadError as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Malformed YAML:\n\n{}\n\n".format(e)) from e
    except Exception as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Severely malformed YAML:\n\n{}\n\n".format(e)) from e

    if type(contents) != Node:
        # Special case allowance for None, when the loaded file has only comments in it.
        if contents is None:
            contents = Node({}, file_index, 0, 0)
        else:
            raise LoadError(LoadErrorReason.INVALID_YAML,
                            "YAML file has content of type '{}' instead of expected type 'dict': {}"
                            .format(type(contents[0]).__name__, file_name))

    # Store this away because we'll use it later for "top level" provenance
    if file_index is not None:
        f_info = <FileInfo> _FILE_LIST[file_index]

        _FILE_LIST[file_index] = FileInfo(
            f_info.filename,
            f_info.shortname,
            f_info.displayname,
            contents,
            f_info.project,
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
def dump(object contents, str filename=None):
    roundtrip_dump(node_sanitize(contents), file=filename)


# node_get_provenance()
#
# Gets the provenance for a node
#
# Args:
#   node (Node): a dictionary
#   key (str): key in the dictionary
#   indices (list of indexes): Index path, in the case of list values
#
# Returns: The Provenance of the dict, member or list element
#
cpdef ProvenanceInformation node_get_provenance(Node node, str key=None, list indices=None):
    assert type(node.value) is dict

    if key is None:
        # Retrieving the provenance for this node directly
        return ProvenanceInformation(node)

    if key and not indices:
        return ProvenanceInformation(node.value.get(key))

    cdef Node nodeish = <Node> node.value.get(key)
    for idx in indices:
        nodeish = <Node> nodeish.value[idx]

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
cpdef object node_get(Node node, object expected_type, str key, list indices=None, object default_value=_sentinel, bint allow_none=False):
    if indices is None:
        value = node.value.get(key, _sentinel)

        if value is _sentinel:
            if default_value is _sentinel:
                provenance = node_get_provenance(node)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Dictionary did not contain expected key '{}'".format(provenance, key))

            value = Node(default_value, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter())
    else:
        # Implied type check of the element itself
        # No need to synthesise useful node content as we destructure it immediately
        value = Node(node_get(node, list, key), _SYNTHETIC_FILE_INDEX, 0, 0)
        for index in indices:
            value = value.value[index]
            if type(value) is not Node:
                value = Node(value, _SYNTHETIC_FILE_INDEX, 0, 0)

    # Optionally allow None as a valid value for any type
    if value.value is None and (allow_none or default_value is None):
        return None

    if (expected_type is not None) and (type(value.value) is not expected_type):
        # Attempt basic conversions if possible, typically we want to
        # be able to specify numeric values and convert them to strings,
        # but we dont want to try converting dicts/lists
        try:
            if expected_type == bool and type(value.value) is str:
                # Dont coerce booleans to string, this makes "False" strings evaluate to True
                # We don't structure into full nodes since there's no need.
                if value.value in ('True', 'true'):
                    value = Node(True, _SYNTHETIC_FILE_INDEX, 0, 0)
                elif value.value in ('False', 'false'):
                    value = Node(False, _SYNTHETIC_FILE_INDEX, 0, 0)
                else:
                    raise ValueError()
            elif not (expected_type == list or
                      expected_type == dict or
                      isinstance(value.value, (list, dict))):
                value = Node(expected_type(value.value), _SYNTHETIC_FILE_INDEX, 0, 0)
            else:
                raise ValueError()
        except (ValueError, TypeError):
            provenance = node_get_provenance(node, key=key, indices=indices)
            if indices:
                path = [key, *["[{:d}]".format(i) for i in indices]]
                path = "".join(path)
            else:
                path = key
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, expected_type.__name__))

    # Now collapse lists, and scalars, to their value, leaving nodes as-is
    if type(value.value) is not dict:
        value = value.value

    # Trim it at the bud, let all loaded strings from yaml be stripped of whitespace
    if type(value) is str:
        value = value.strip()

    elif type(value) is list:
        # Now we create a fresh list which unwraps the str and list types
        # semi-recursively.
        value = __trim_list_provenance(value)

    return value


cdef list __trim_list_provenance(list value):
    cdef list ret = []
    for entry in value:
        if type(entry) is not Node:
            entry = Node(entry, _SYNTHETIC_FILE_INDEX, 0, 0)
        if type(entry.value) is list:
            ret.append(__trim_list_provenance(entry.value))
        elif type(entry.value) is dict:
            ret.append(entry)
        else:
            ret.append(entry.value)
    return ret


# node_set()
#
# Set an item within the node.  If using `indices` be aware that the entry must
# already exist, or else a KeyError will be raised.  Use `node_extend_list` to
# create entries before using `node_set`
#
# Args:
#    node (Node): The node
#    key (str): The key name
#    value: The value
#    indices: Any indices to index into the list referenced by key, like in
#             `node_get` (must be a list of integers)
#
cpdef void node_set(Node node, object key, object value, list indices=None) except *:
    cdef int idx

    if indices:
        node = <Node> (<dict> node.value)[key]
        key = indices.pop()
        for idx in indices:
            node = <Node> (<list> node.value)[idx]
    if type(value) is Node:
        node.value[key] = value
    else:
        try:
            # Need to do this just in case we're modifying a list
            old_value = <Node> node.value[key]
        except KeyError:
            old_value = None
        if old_value is None:
            node.value[key] = Node(value, node.file_index, node.line, next_synthetic_counter())
        else:
            node.value[key] = Node(value, old_value.file_index, old_value.line, old_value.column)


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
def node_extend_list(Node node, str key, Py_ssize_t length, object default):
    assert type(default) is str or default in ([], {})

    cdef Node list_node = <Node> node.value.get(key)
    if list_node is None:
        list_node = node.value[key] = Node([], node.file_index, node.line, next_synthetic_counter())

    cdef list the_list = list_node.value
    def_type = type(default)

    file_index = node.file_index
    if the_list:
        line_num = the_list[-1][2]
    else:
        line_num = list_node.line

    while length > len(the_list):
        if def_type is str:
            value = default
        elif def_type is list:
            value = []
        else:
            value = {}

        line_num += 1

        the_list.append(Node(value, file_index, line_num, next_synthetic_counter()))


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
        node = Node(node, _SYNTHETIC_FILE_INDEX, 0, 0)

    cdef str key

    for key, value in node.value.items():
        if type(value) is not Node:
            value = Node(value, _SYNTHETIC_FILE_INDEX, 0, 0)
        if type(value.value) is dict:
            yield (key, value)
        elif type(value.value) is list:
            yield (key, __trim_list_provenance(value.value))
        else:
            yield (key, value.value)


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
cpdef list node_keys(object node):
    if type(node) is Node:
        return list((<Node> node).value.keys())
    return list(node.keys())


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
def node_del(Node node, str key, bint safe=False):
    try:
        del node.value[key]
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
    assert (type(maybenode) is not Node) or (type(maybenode.value) is dict)
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
def new_synthetic_file(str filename, object project=None):
    cdef Py_ssize_t file_index = len(_FILE_LIST)
    cdef Node node = Node({}, file_index, 0, 0)

    _FILE_LIST.append(FileInfo(filename,
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
def new_empty_node(Node ref_node=None):
    if ref_node is not None:
        return Node({}, ref_node.file_index, ref_node.line, next_synthetic_counter())
    else:
        return Node({}, _SYNTHETIC_FILE_INDEX, 0, 0)


# new_node_from_dict()
#
# Args:
#   indict (dict): The input dictionary
#
# Returns:
#   (Node): A new synthetic YAML tree which represents this dictionary
#
cpdef Node new_node_from_dict(dict indict):
    cdef dict ret = {}
    cdef str k
    for k, v in indict.items():
        vtype = type(v)
        if vtype is dict:
            ret[k] = new_node_from_dict(v)
        elif vtype is list:
            ret[k] = __new_node_from_list(v)
        else:
            ret[k] = Node(str(v), _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter())
    return Node(ret, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter())


# Internal function to help new_node_from_dict() to handle lists
cdef Node __new_node_from_list(list inlist):
    cdef list ret = []
    for v in inlist:
        vtype = type(v)
        if vtype is dict:
            ret.append(new_node_from_dict(v))
        elif vtype is list:
            ret.append(__new_node_from_list(v))
        else:
            ret.append(Node(str(v), _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter()))
    return Node(ret, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter())


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
cdef bint _is_composite_list(Node node):
    cdef bint has_directives = False
    cdef bint has_keys = False
    cdef str key

    if type(node.value) is dict:
        for key in node_keys(node):
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
cdef void _compose_composite_list(Node target, Node source):
    clobber = source.value.get("(=)")
    prefix = source.value.get("(<)")
    suffix = source.value.get("(>)")
    if clobber is not None:
        # We want to clobber the target list
        # which basically means replacing the target list
        # with ourselves
        target.value["(=)"] = clobber
        if prefix is not None:
            target.value["(<)"] = prefix
        elif "(<)" in target.value:
            target.value["(<)"].value.clear()
        if suffix is not None:
            target.value["(>)"] = suffix
        elif "(>)" in target.value:
            target.value["(>)"].value.clear()
    else:
        # Not clobbering, so prefix the prefix and suffix the suffix
        if prefix is not None:
            if "(<)" in target.value:
                for v in reversed(prefix.value):
                    target.value["(<)"].value.insert(0, v)
            else:
                target.value["(<)"] = prefix
        if suffix is not None:
            if "(>)" in target.value:
                target.value["(>)"].value.extend(suffix.value)
            else:
                target.value["(>)"] = suffix


# _compose_list()
#
# Compose a composite list (a dict with composition directives) on top of a
# simple list.
#
# Args:
#    target (Node): The target list to be composed into
#    source (Node): The composition list to be composed from
#
cdef void _compose_list(Node target, Node source):
    clobber = source.value.get("(=)")
    prefix = source.value.get("(<)")
    suffix = source.value.get("(>)")
    if clobber is not None:
        target.value.clear()
        target.value.extend(clobber.value)
    if prefix is not None:
        for v in reversed(prefix.value):
            target.value.insert(0, v)
    if suffix is not None:
        target.value.extend(suffix.value)


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
cpdef void composite_dict(Node target, Node source, list path=None) except *:
    cdef str k
    cdef Node v, target_value

    if path is None:
        path = []
    for k, v in source.value.items():
        path.append(k)
        if type(v.value) is list:
            # List clobbers anything list-like
            target_value = target.value.get(k)
            if not (target_value is None or
                    type(target_value.value) is list or
                    _is_composite_list(target_value)):
                raise CompositeError(path,
                                     "{}: List cannot overwrite {} at: {}"
                                     .format(node_get_provenance(source, k),
                                             k,
                                             node_get_provenance(target, k)))
            # Looks good, clobber it
            target.value[k] = v
        elif _is_composite_list(v):
            if k not in target.value:
                # Composite list clobbers empty space
                target.value[k] = v
            elif type(target.value[k].value) is list:
                # Composite list composes into a list
                _compose_list(target.value[k], v)
            elif _is_composite_list(target.value[k]):
                # Composite list merges into composite list
                _compose_composite_list(target.value[k], v)
            else:
                # Else composing on top of normal dict or a scalar, so raise...
                raise CompositeError(path,
                                     "{}: Cannot compose lists onto {}".format(
                                         node_get_provenance(v),
                                         node_get_provenance(target.value[k])))
        elif type(v.value) is dict:
            # We're composing a dict into target now
            if k not in target.value:
                # Target lacks a dict at that point, make a fresh one with
                # the same provenance as the incoming dict
                target.value[k] = Node({}, v.file_index, v.line, v.column)
            if type(target.value) is not dict:
                raise CompositeError(path,
                                     "{}: Cannot compose dictionary onto {}".format(
                                         node_get_provenance(v),
                                         node_get_provenance(target.value[k])))
            composite_dict(target.value[k], v, path)
        else:
            target_value = target.value.get(k)
            if target_value is not None and type(target_value.value) is not str:
                raise CompositeError(path,
                                     "{}: Cannot compose scalar on non-scalar at {}".format(
                                         node_get_provenance(v),
                                         node_get_provenance(target.value[k])))
            target.value[k] = v
        path.pop()


# Like composite_dict(), but raises an all purpose LoadError for convenience
#
cpdef void composite(Node target, Node source) except *:
    assert type(source.value) is dict
    assert type(target.value) is dict

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
def composite_and_move(Node target, Node source):
    composite(source, target)

    cdef str key
    cdef Node value
    cdef list to_delete = [key for key in target.value.keys() if key not in source.value]
    for key, value in source.value.items():
        target.value[key] = value
    for key in to_delete:
        del target.value[key]


# Types we can short-circuit in node_sanitize for speed.
__SANITIZE_SHORT_CIRCUIT_TYPES = (int, float, str, bool)


# node_sanitize()
#
# Returns an alphabetically ordered recursive copy
# of the source node with internal provenance information stripped.
#
# Only dicts are ordered, list elements are left in order.
#
cpdef object node_sanitize(object node, object dict_type=OrderedDict):
    node_type = type(node)

    # If we have an unwrappable node, unwrap it
    if node_type is Node:
        node = node.value
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
        return tuple([node_sanitize(v, dict_type=dict_type) for v in node])

    # Everything else just gets returned as-is.
    return node


# node_validate()
#
# Validate the node so as to ensure the user has not specified
# any keys which are unrecognized by buildstream (usually this
# means a typo which would otherwise not trigger an error).
#
# Args:
#    node (Node): A dictionary loaded from YAML
#    valid_keys (list): A list of valid keys for the specified node
#
# Raises:
#    LoadError: In the case that the specified node contained
#               one or more invalid keys
#
cpdef void node_validate(Node node, list valid_keys) except *:

    # Probably the fastest way to do this: https://stackoverflow.com/a/23062482
    cdef set valid_keys_set = set(valid_keys)
    cdef str key

    for key in node.value:
        if key not in valid_keys_set:
            provenance = node_get_provenance(node, key=key)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Unexpected key: {}".format(provenance, key))


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
cpdef Node node_copy(Node source):
    cdef dict copy = {}
    cdef str key
    cdef Node value

    for key, value in source.value.items():
        value_type = type(value.value)
        if value_type is dict:
            copy[key] = node_copy(value)
        elif value_type is list:
            copy[key] = _list_copy(value)
        elif value_type in __QUICK_TYPES:
            copy[key] = value
        else:
            raise ValueError("Unable to be quick about node_copy of {}".format(value_type))

    return Node(copy, source.file_index, source.line, source.column)


# Internal function to help node_copy() but for lists.
cdef Node _list_copy(Node source):
    cdef list copy = []
    for item in source.value:
        if type(item) is Node:
            item_type = type(item.value)
        else:
            item_type = type(item)

        if item_type is dict:
            copy.append(node_copy(item))
        elif item_type is list:
            copy.append(_list_copy(item))
        elif item_type in __QUICK_TYPES:
            copy.append(item)
        else:
            raise ValueError("Unable to be quick about list_copy of {}".format(item_type))

    return Node(copy, source.file_index, source.line, source.column)


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
cpdef void node_final_assertions(Node node) except *:
    cdef str key
    cdef Node value

    for key, value in node.value.items():

        # Assert that list composition directives dont remain, this
        # indicates that the user intended to override a list which
        # never existed in the underlying data
        #
        if key in __NODE_ASSERT_COMPOSITION_DIRECTIVES:
            provenance = node_get_provenance(node, key)
            raise LoadError(LoadErrorReason.TRAILING_LIST_DIRECTIVE,
                            "{}: Attempt to override non-existing list".format(provenance))

        value_type = type(value.value)

        if value_type is dict:
            node_final_assertions(value)
        elif value_type is list:
            _list_final_assertions(value)


# Helper function for node_final_assertions(), but for lists.
def _list_final_assertions(Node values):
    for value in values.value:
        value_type = type(value.value)

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
def assert_symbol_name(ProvenanceInformation provenance, str symbol_name, str purpose, *, bint allow_dashes=True):
    cdef str valid_chars = string.digits + string.ascii_letters + '_'
    if allow_dashes:
        valid_chars += '-'

    cdef bint valid = True
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
# If the key is provided, then we actually hunt for the node represented by
# target[key] and return its container, rather than hunting for target directly
#
# Args:
#    node (Node): The node at the root of the tree to search
#    target (Node): The node you are looking for in that tree
#    key (str): Optional string key within target node
#
# Returns:
#    (list): A path from `node` to `target` or None if `target` is not in the subtree
cpdef list node_find_target(Node node, Node target, str key=None):
    if key is not None:
        target = target.value[key]

    cdef list path = []
    if _walk_find_target(node, path, target):
        if key:
            # Remove key from end of path
            path = path[:-1]
        return path
    return None


# Helper for node_find_target() which walks a value
cdef bint _walk_find_target(Node node, list path, Node target):
    if node.file_index == target.file_index and node.line == target.line and node.column == target.column:
        return True
    elif type(node.value) is dict:
        return _walk_dict_node(node, path, target)
    elif type(node.value) is list:
        return _walk_list_node(node, path, target)
    return False


# Helper for node_find_target() which walks a list
cdef bint _walk_list_node(Node node, list path, Node target):
    cdef int i
    cdef Node v

    for i, v in enumerate(node.value):
        path.append(i)
        if _walk_find_target(v, path, target):
            return True
        del path[-1]
    return False


# Helper for node_find_target() which walks a mapping
cdef bint _walk_dict_node(Node node, list path, Node target):
    cdef str k
    cdef Node v

    for k, v in node.value.items():
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
