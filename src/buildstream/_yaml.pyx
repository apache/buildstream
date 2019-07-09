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

import datetime
import sys
import string
from contextlib import ExitStack
from collections import OrderedDict
from collections.abc import Mapping

from ruamel import yaml

from ._exceptions import LoadError, LoadErrorReason


# Without this, pylint complains about all the `type(foo) is blah` checks
# because it feels isinstance() is more idiomatic.  Sadly, it is much slower to
# do `isinstance(foo, blah)` for reasons I am unable to fathom.  As such, we
# blanket disable the check for this module.
#
# pylint: disable=unidiomatic-typecheck


# A sentinel to be used as a default argument for functions that need
# to distinguish between a kwarg set to None and an unset kwarg.
_sentinel = object()


# Node()
#
# Container for YAML loaded data and its provenance
#
# All nodes returned (and all internal lists/strings) have this type (rather
# than a plain tuple, to distinguish them in things like node_sanitize)
#
# Members:
#   file_index (int): Index within _FILE_LIST (a list of loaded file paths).
#                     Negative indices indicate synthetic nodes so that
#                     they can be referenced.
#   line (int): The line number within the file where the value appears.
#   col (int): The column number within the file where the value appears.
#
cdef class Node:

    def __init__(self, int file_index, int line, int column):
        self.file_index = file_index
        self.line = line
        self.column = column

    @classmethod
    def from_dict(cls, dict value):
        if value:
            return _new_node_from_dict(value, MappingNode({}, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter()))
        else:
            # We got an empty dict, we can shortcut
            return MappingNode({}, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter())

    cdef bint _walk_find(self, Node target, list path) except *:
        raise NotImplementedError()

    cdef bint _shares_position_with(self, Node target):
        return self.file_index == target.file_index and self.line == target.line and self.column == target.column

    def __contains__(self, what):
        # Delegate to the inner value, though this will likely not work
        # very well if the node is a list or string, it's unlikely that
        # code which has access to such nodes would do this.
        return what in (<MappingNode> self).value

    cpdef Node copy(self):
        raise NotImplementedError()

    cpdef object strip_node_info(self):
        raise NotImplementedError()

    # _assert_fully_composited()
    #
    # This must be called on a fully loaded and composited node,
    # after all composition has completed.
    #
    # This checks that no more composition directives are present
    # in the data.
    #
    # Raises:
    #    (LoadError): If any assertions fail
    #
    cpdef void _assert_fully_composited(self) except *:
        raise NotImplementedError()

    # _is_composite_list
    #
    # Checks if the node is a Mapping with array composition
    # directives.
    #
    # Returns:
    #    (bool): True if node was a Mapping containing only
    #            list composition directives
    #
    # Raises:
    #    (LoadError): If node was a mapping and contained a mix of
    #                 list composition directives and other keys
    #
    cdef bint _is_composite_list(self) except *:
        raise NotImplementedError()

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        raise NotImplementedError()

    def __json__(self):
        raise ValueError("Nodes should not be allowed when jsonify-ing data", self)


cdef class ScalarNode(Node):

    def __init__(self, object value, int file_index, int line, int column):
        super().__init__(file_index, line, column)

        cdef value_type = type(value)

        if value_type is str:
            value = value.strip()
        elif value_type is bool:
            if value:
                value = "True"
            else:
                value = "False"
        elif value_type is int:
            value = str(value)
        elif value is None:
            pass
        else:
            raise ValueError("ScalarNode can only hold str, int, bool or None objects")

        self.value = value

    cpdef ScalarNode copy(self):
        return self

    cpdef bint is_none(self):
        return self.value is None

    cpdef bint as_bool(self) except *:
        if type(self.value) is bool:
            return self.value

        # Don't coerce booleans to string, this makes "False" strings evaluate to True
        if self.value in ('True', 'true'):
            return True
        elif self.value in ('False', 'false'):
            return False
        else:
            provenance = node_get_provenance(self)
            path = provenance.toplevel._find(self)[-1]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                "{}: Value of '{}' is not of the expected type '{}'"
                .format(provenance, path, bool.__name__, self.value))

    cpdef int as_int(self) except *:
        try:
            return int(self.value)
        except ValueError:
            provenance = node_get_provenance(self)
            path = provenance.toplevel._find(self)[-1]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                "{}: Value of '{}' is not of the expected type '{}'"
                .format(provenance, path, int.__name__))

    cpdef str as_str(self):
        # We keep 'None' as 'None' to simplify the API's usage and allow chaining for users
        if self.value is None:
            return None
        return str(self.value)

    cpdef object strip_node_info(self):
        return self.value

    cpdef void _assert_fully_composited(self) except *:
        pass

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        cdef Node target_value = target.value.get(key)

        if target_value is not None and type(target_value) is not ScalarNode:
            raise CompositeError(path,
                                 "{}: Cannot compose scalar on non-scalar at {}".format(
                                    node_get_provenance(self),
                                    node_get_provenance(target_value)))

        target.value[key] = self

    cdef bint _is_composite_list(self) except *:
        return False

    cdef bint _walk_find(self, Node target, list path) except *:
        return self._shares_position_with(target)


cdef class MappingNode(Node):

    def __init__(self, dict value, int file_index, int line, int column):
        super().__init__(file_index, line, column)
        self.value = value

    cpdef MappingNode copy(self):
        cdef dict copy = {}
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            copy[key] = value.copy()

        return MappingNode(copy, self.file_index, self.line, self.column)

    # find()
    #
    # Searches the given node tree for the given target node.
    #
    # This is typically used when trying to walk a path to a given node
    # for the purpose of then modifying a similar tree of objects elsewhere
    #
    # Args:
    #    target (Node): The node you are looking for in that tree
    #
    # Returns:
    #    (list): A path from `node` to `target` or None if `target` is not in the subtree
    cpdef list _find(self, Node target):
        cdef list path = []
        if self._walk_find(target, path):
            return path
        return None

    # composite()
    #
    # Compose one mapping node onto another
    #
    # Args:
    #    target (Node): The target to compose into
    #
    # Raises: LoadError
    #
    cpdef void composite(self, MappingNode target) except *:
        try:
            self._composite(target, [])
        except CompositeError as e:
            source_provenance = node_get_provenance(self)
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
    cpdef void composite_under(self, MappingNode target) except *:
        target.composite(self)

        cdef str key
        cdef Node value
        cdef list to_delete = [key for key in target.value.keys() if key not in self.value]

        for key, value in self.value.items():
            target.value[key] = value
        for key in to_delete:
            del target.value[key]

    cdef Node get(self, str key, object default, object default_constructor):
        value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if default is _sentinel:
                provenance = node_get_provenance(self)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Dictionary did not contain expected key '{}'".format(provenance, key))

            if default is None:
                value = None
            else:
                value = default_constructor(default, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter())

        return value

    cpdef MappingNode get_mapping(self, str key, object default=_sentinel):
        value = self.get(key, default, MappingNode)

        if type(value) is not MappingNode and value is not None:
            provenance = node_get_provenance(value)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type 'Mapping'"
                            .format(provenance, key))

        return value

    cpdef Node get_node(self, str key, list allowed_types = None, bint allow_none = False):
        cdef value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if allow_none:
                return None

            provenance = node_get_provenance(self)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dictionary did not contain expected key '{}'".format(provenance, key))

        if allowed_types and type(value) not in allowed_types:
            provenance = node_get_provenance(self)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not one of the following: {}.".format(
                                provenance, key, ", ".join(allowed_types)))

        return value

    cpdef ScalarNode get_scalar(self, str key, object default=_sentinel):
        value = self.get(key, default, ScalarNode)

        if type(value) is not ScalarNode:
            if value is None:
                value = ScalarNode(None, self.file_index, 0, next_synthetic_counter())
            else:
                provenance = node_get_provenance(value)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Value of '{}' is not of the expected type 'Scalar'"
                                .format(provenance, key))

        return value

    cpdef SequenceNode get_sequence(self, str key, object default=_sentinel):
        value = self.get(key, default, SequenceNode)

        if type(value) is not SequenceNode and value is not None:
            provenance = node_get_provenance(value)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type 'Sequence'"
                            .format(provenance, key))

        return value

    cpdef bint get_bool(self, str key, object default=_sentinel) except *:
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_bool()

    cpdef int get_int(self, str key, object default=_sentinel) except *:
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_int()

    cpdef str get_str(self, str key, object default=_sentinel):
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_str()

    cpdef object items(self):
        return self.value.items()

    cpdef list keys(self):
        return list(self.value.keys())

    cpdef void safe_del(self, str key):
        try:
            del self.value[key]
        except KeyError:
            pass

    # validate_keys()
    #
    # Validate the node so as to ensure the user has not specified
    # any keys which are unrecognized by buildstream (usually this
    # means a typo which would otherwise not trigger an error).
    #
    # Args:
    #    valid_keys (list): A list of valid keys for the specified node
    #
    # Raises:
    #    LoadError: In the case that the specified node contained
    #               one or more invalid keys
    #
    cpdef void validate_keys(self, list valid_keys) except *:
        # Probably the fastest way to do this: https://stackoverflow.com/a/23062482
        cdef set valid_keys_set = set(valid_keys)
        cdef str key

        for key in self.value:
            if key not in valid_keys_set:
                provenance = node_get_provenance(self, key=key)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Unexpected key: {}".format(provenance, key))

    cpdef object values(self):
        return self.value.values()

    cpdef object strip_node_info(self):
        cdef str key
        cdef Node value

        return {key: value.strip_node_info() for key, value in self.value.items()}

    cdef void _composite(self, MappingNode target, list path=None) except *:
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            path.append(key)
            value._compose_on(key, target, path)
            path.pop()

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        cdef Node target_value

        if self._is_composite_list():
            if key not in target.value:
                # Composite list clobbers empty space
                target.value[key] = self
            else:
                target_value = target.value[key]

                if type(target_value) is SequenceNode:
                    # Composite list composes into a list
                    self._compose_on_list(target_value)
                elif target_value._is_composite_list():
                    # Composite list merges into composite list
                    self._compose_on_composite_dict(target_value)
                else:
                    # Else composing on top of normal dict or a scalar, so raise...
                    raise CompositeError(path,
                                         "{}: Cannot compose lists onto {}".format(
                                             node_get_provenance(self),
                                             node_get_provenance(target_value)))
        else:
            # We're composing a dict into target now
            if key not in target.value:
                # Target lacks a dict at that point, make a fresh one with
                # the same provenance as the incoming dict
                target.value[key] = MappingNode({}, self.file_index, self.line, self.column)

            self._composite(target.value[key], path)

    cdef void _compose_on_list(self, SequenceNode target):
        cdef SequenceNode clobber = self.value.get("(=)")
        cdef SequenceNode prefix = self.value.get("(<)")
        cdef SequenceNode suffix = self.value.get("(>)")

        if clobber is not None:
            target.value.clear()
            target.value.extend(clobber.value)
        if prefix is not None:
            for v in reversed(prefix.value):
                target.value.insert(0, v)
        if suffix is not None:
            target.value.extend(suffix.value)

    cdef void _compose_on_composite_dict(self, MappingNode target):
        cdef SequenceNode clobber = self.value.get("(=)")
        cdef SequenceNode prefix = self.value.get("(<)")
        cdef SequenceNode suffix = self.value.get("(>)")

        if clobber is not None:
            # We want to clobber the target list
            # which basically means replacing the target list
            # with ourselves
            target.value["(=)"] = clobber
            if prefix is not None:
                target.value["(<)"] = prefix
            elif "(<)" in target.value:
                (<SequenceNode> target.value["(<)"]).value.clear()
            if suffix is not None:
                target.value["(>)"] = suffix
            elif "(>)" in target.value:
                (<SequenceNode> target.value["(>)"]).value.clear()
        else:
            # Not clobbering, so prefix the prefix and suffix the suffix
            if prefix is not None:
                if "(<)" in target.value:
                    for v in reversed(prefix.value):
                        (<SequenceNode> target.value["(<)"]).value.insert(0, v)
                else:
                    target.value["(<)"] = prefix
            if suffix is not None:
                if "(>)" in target.value:
                    (<SequenceNode> target.value["(>)"]).value.extend(suffix.value)
                else:
                    target.value["(>)"] = suffix

    cdef bint _is_composite_list(self) except *:
        cdef bint has_directives = False
        cdef bint has_keys = False
        cdef str key

        for key in self.value.keys():
            if key in ['(>)', '(<)', '(=)']:
                has_directives = True
            else:
                has_keys = True

        if has_keys and has_directives:
            provenance = node_get_provenance(self)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dictionary contains array composition directives and arbitrary keys"
                            .format(provenance))

        return has_directives

    def __delitem__(self, str key):
        del self.value[key]

    def __setitem__(self, str key, object value):
        cdef Node old_value

        if type(value) in [MappingNode, ScalarNode, SequenceNode]:
            self.value[key] = value
        else:
            node = _create_node_recursive(value, self)

            # FIXME: Do we really want to override provenance?
            #
            # Related to https://gitlab.com/BuildStream/buildstream/issues/1058
            #
            # There are only two cases were nodes are set in the code (hence without provenance):
            #   - When automatic variables are set by the core (e-g: max-jobs)
            #   - when plugins call Element.set_public_data
            #
            # The first case should never throw errors, so it is of limited interests.
            #
            # The second is more important. What should probably be done here is to have 'set_public_data'
            # able of creating a fake provenance with the name of the plugin, the project and probably the
            # element name.
            #
            # We would therefore have much better error messages, and would be able to get rid of most synthetic
            # nodes.
            old_value = self.value.get(key)
            if old_value:
                node.file_index = old_value.file_index
                node.line = old_value.line
                node.column = old_value.column

            self.value[key] = node

    cpdef void _assert_fully_composited(self) except *:
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            # Assert that list composition directives dont remain, this
            # indicates that the user intended to override a list which
            # never existed in the underlying data
            #
            if key in ('(>)', '(<)', '(=)'):
                provenance = node_get_provenance(value)
                raise LoadError(LoadErrorReason.TRAILING_LIST_DIRECTIVE,
                                "{}: Attempt to override non-existing list".format(provenance))

            value._assert_fully_composited()

    cdef bint _walk_find(self, Node target, list path) except *:
        cdef str k
        cdef Node v

        if self._shares_position_with(target):
            return True

        for k, v in self.value.items():
            path.append(k)
            if v._walk_find(target, path):
                return True
            del path[-1]

        return False



cdef class SequenceNode(Node):
    def __init__(self, list value, int file_index, int line, int column):
        super().__init__(file_index, line, column)
        self.value = value

    cpdef void append(self, object value):
        if type(value) in [MappingNode, ScalarNode, SequenceNode]:
            self.value.append(value)
        else:
            node = _create_node_recursive(value, self)
            self.value.append(node)

    cpdef SequenceNode copy(self):
        cdef list copy = []
        cdef Node entry

        for entry in self.value:
            copy.append(entry.copy())

        return SequenceNode(copy, self.file_index, self.line, self.column)

    cpdef MappingNode mapping_at(self, int index):
        value = self.value[index]

        if type(value) is not MappingNode:
            provenance = node_get_provenance(self)
            path = ["[{}]".format(p) for p in provenance.toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, MappingNode.__name__))
        return value

    cpdef Node node_at(self, int key, list allowed_types = None):
        cdef value = self.value[key]

        if allowed_types and type(value) not in allowed_types:
            provenance = node_get_provenance(self)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not one of the following: {}.".format(
                                provenance, key, ", ".join(allowed_types)))

        return value

    cpdef SequenceNode sequence_at(self, int index):
        value = self.value[index]

        if type(value) is not SequenceNode:
            provenance = node_get_provenance(self)
            path = ["[{}]".format(p) for p in provenance.toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, SequenceNode.__name__))

        return value

    cpdef list as_str_list(self):
        return [node.as_str() for node in self.value]

    cpdef object strip_node_info(self):
        cdef Node value
        return [value.strip_node_info() for value in self.value]

    cpdef void _assert_fully_composited(self) except *:
        cdef Node value
        for value in self.value:
            value._assert_fully_composited()

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        # List clobbers anything list-like
        cdef Node target_value = target.value.get(key)

        if not (target_value is None or
                type(target_value) is SequenceNode or
                target_value._is_composite_list()):
            raise CompositeError(path,
                                 "{}: List cannot overwrite {} at: {}"
                                 .format(node_get_provenance(self),
                                         key,
                                         node_get_provenance(target_value)))
        # Looks good, clobber it
        target.value[key] = self

    cdef bint _is_composite_list(self) except *:
        return False

    cdef bint _walk_find(self, Node target, list path) except *:
        cdef int i
        cdef Node v

        if self._shares_position_with(target):
            return True

        for i, v in enumerate(self.value):
            path.append(i)
            if v._walk_find(target, path):
                return True
            del path[-1]

        return False

    def __iter__(self):
        return iter(self.value)

    def __len__(self):
        return len(self.value)

    def __reversed__(self):
        return reversed(self.value)

    def __setitem__(self, int key, object value):
        cdef Node old_value

        if type(value) in [MappingNode, ScalarNode, SequenceNode]:
            self.value[key] = value
        else:
            node = _create_node_recursive(value, self)

            # FIXME: Do we really want to override provenance?
            # See __setitem__ on 'MappingNode' for more context
            old_value = self.value[key]
            if old_value:
                node.file_index = old_value.file_index
                node.line = old_value.line
                node.column = old_value.column

            self.value[key] = node

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
        if (nodeish is None) or (nodeish.file_index == _SYNTHETIC_FILE_INDEX):
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
        super().__init__(message)
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
        newmap = MappingNode({}, self._file_index, ev.start_mark.line, ev.start_mark.column)
        self.output.append(newmap)
        return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_key_ScalarEvent(self, object ev):
        self.keys.append(ev.value)
        return RepresenterState.wait_value

    cdef RepresenterState _handle_wait_value_ScalarEvent(self, object ev):
        key = self.keys.pop()
        (<MappingNode> self.output[-1]).value[key] = \
            ScalarNode(ev.value, self._file_index, ev.start_mark.line, ev.start_mark.column)
        return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_value_MappingStartEvent(self, object ev):
        cdef RepresenterState new_state = self._handle_doc_MappingStartEvent(ev)
        key = self.keys.pop()
        (<MappingNode> self.output[-2]).value[key] = self.output[-1]
        return new_state

    cdef RepresenterState _handle_wait_key_MappingEndEvent(self, object ev):
        # We've finished a mapping, so pop it off the output stack
        # unless it's the last one in which case we leave it
        if len(self.output) > 1:
            self.output.pop()
            if type(self.output[-1]) is SequenceNode:
                return RepresenterState.wait_list_item
            else:
                return RepresenterState.wait_key
        else:
            return RepresenterState.doc

    cdef RepresenterState _handle_wait_value_SequenceStartEvent(self, object ev):
        self.output.append(SequenceNode([], self._file_index, ev.start_mark.line, ev.start_mark.column))
        (<MappingNode> self.output[-2]).value[self.keys[-1]] = self.output[-1]
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_SequenceStartEvent(self, object ev):
        self.keys.append(len((<SequenceNode> self.output[-1]).value))
        self.output.append(SequenceNode([], self._file_index, ev.start_mark.line, ev.start_mark.column))
        (<SequenceNode> self.output[-2]).value.append(self.output[-1])
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
        (<SequenceNode> self.output[-1]).value.append(
           ScalarNode(ev.value, self._file_index, ev.start_mark.line, ev.start_mark.column))
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_MappingStartEvent(self, object ev):
        cdef RepresenterState new_state = self._handle_doc_MappingStartEvent(ev)
        (<SequenceNode> self.output[-2]).value.append(self.output[-1])
        return new_state

    cdef RepresenterState _handle_doc_DocumentEndEvent(self, object ev):
        if len(self.output) != 1:
            raise YAMLLoadError("Zero, or more than one document found in YAML stream")
        return RepresenterState.stream

    cdef RepresenterState _handle_stream_StreamEndEvent(self, object ev):
        return RepresenterState.init


cdef Node _create_node_recursive(object value, Node ref_node):
    cdef value_type = type(value)

    if value_type is list:
        node = _new_node_from_list(value, ref_node)
    elif value_type is str:
        node = ScalarNode(value, ref_node.file_index, ref_node.line, next_synthetic_counter())
    elif value_type is dict:
        node = _new_node_from_dict(value, ref_node)
    else:
        raise ValueError(
            "Unable to assign a value of type {} to a Node.".format(value_type))

    return node


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

    if type(contents) != MappingNode:
        # Special case allowance for None, when the loaded file has only comments in it.
        if contents is None:
            contents = MappingNode({}, file_index, 0, 0)
        else:
            raise LoadError(LoadErrorReason.INVALID_YAML,
                            "YAML file has content of type '{}' instead of expected type 'dict': {}"
                            .format(type(contents[0]).__name__, file_name))

    # Store this away because we'll use it later for "top level" provenance
    if file_index != _SYNTHETIC_FILE_INDEX:
        f_info = <FileInfo> _FILE_LIST[file_index]

        _FILE_LIST[file_index] = FileInfo(
            f_info.filename,
            f_info.shortname,
            f_info.displayname,
            contents,
            f_info.project,
        )

    if copy_tree:
        contents = contents.copy()
    return contents


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
    if key is None:
        # Retrieving the provenance for this node directly
        return ProvenanceInformation(node)

    if key and not indices:
        return ProvenanceInformation((<MappingNode> node).value.get(key))

    cdef Node nodeish = <Node> (<MappingNode> node).value.get(key)
    for idx in indices:
        nodeish = <Node> (<SequenceNode> nodeish).value[idx]

    return ProvenanceInformation(nodeish)


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
    cdef Node node = MappingNode({}, file_index, 0, 0)

    _FILE_LIST.append(FileInfo(filename,
                       filename,
                       "<synthetic {}>".format(filename),
                       node,
                       project))
    return node


# new_node_from_dict()
#
# Args:
#   indict (dict): The input dictionary
#
# Returns:
#   (Node): A new synthetic YAML tree which represents this dictionary
#
cdef Node _new_node_from_dict(dict indict, Node ref_node):
    cdef MappingNode ret = MappingNode({}, ref_node.file_index, ref_node.line, next_synthetic_counter())
    cdef str k

    for k, v in indict.items():
        vtype = type(v)
        if vtype is dict:
            ret.value[k] = _new_node_from_dict(v, ref_node)
        elif vtype is list:
            ret.value[k] = _new_node_from_list(v, ref_node)
        else:
            ret.value[k] = ScalarNode(str(v), ref_node.file_index, ref_node.line, next_synthetic_counter())
    return ret


# Internal function to help new_node_from_dict() to handle lists
cdef Node _new_node_from_list(list inlist, Node ref_node):
    cdef SequenceNode ret = SequenceNode([], ref_node.file_index, ref_node.line, next_synthetic_counter())

    for v in inlist:
        vtype = type(v)
        if vtype is dict:
            ret.value.append(_new_node_from_dict(v, ref_node))
        elif vtype is list:
            ret.value.append(_new_node_from_list(v, ref_node))
        else:
            ret.value.append(ScalarNode(str(v), ref_node.file_index, ref_node.line, next_synthetic_counter()))
    return ret


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


###############################################################################

# Roundtrip code

# Represent Nodes automatically

def represent_mapping(self, MappingNode mapping):
    return self.represent_dict(mapping.value)

def represent_scalar(self, ScalarNode scalar):
    return self.represent_str(scalar.value)

def represent_sequence(self, SequenceNode sequence):
    return self.represent_list(sequence.value)


yaml.RoundTripRepresenter.add_representer(MappingNode, represent_mapping)
yaml.RoundTripRepresenter.add_representer(ScalarNode, represent_scalar)
yaml.RoundTripRepresenter.add_representer(SequenceNode, represent_sequence)

# Represent simple types as strings

def represent_as_str(self, value):
    return self.represent_str(str(value))

yaml.RoundTripRepresenter.add_representer(type(None), represent_as_str)
yaml.RoundTripRepresenter.add_representer(int, represent_as_str)
yaml.RoundTripRepresenter.add_representer(float, represent_as_str)
yaml.RoundTripRepresenter.add_representer(bool, represent_as_str)
yaml.RoundTripRepresenter.add_representer(datetime.datetime, represent_as_str)
yaml.RoundTripRepresenter.add_representer(datetime.date, represent_as_str)

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
    with ExitStack() as stack:
        if type(file) is str:
            from . import utils
            f = stack.enter_context(utils.save_file_atomic(file, 'w'))
        elif hasattr(file, 'write'):
            f = file
        else:
            f = sys.stdout
        yaml.round_trip_dump(contents, f, Dumper=HardlineDumper)
