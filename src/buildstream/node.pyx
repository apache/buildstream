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

import string

from ._exceptions import LoadError, LoadErrorReason


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

    def __init__(self):
        raise NotImplementedError("Please do not construct nodes like this. Use Node.from_dict(dict) instead.")

    def __cinit__(self, int file_index, int line, int column, *args):
        self.file_index = file_index
        self.line = line
        self.column = column

    def __json__(self):
        raise ValueError("Nodes should not be allowed when jsonify-ing data", self)

    #############################################################
    #                  Abstract Public Methods                  #
    #############################################################

    cpdef Node copy(self):
        raise NotImplementedError()

    #############################################################
    #                       Public Methods                      #
    #############################################################

    @classmethod
    def from_dict(cls, dict value):
        if value:
            return _new_node_from_dict(value, MappingNode.__new__(
                MappingNode, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter(), {}))
        else:
            # We got an empty dict, we can shortcut
            return MappingNode.__new__(MappingNode, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter(), {})

    cpdef ProvenanceInformation get_provenance(self):
        return ProvenanceInformation(self)

    #############################################################
    #        Abstract Private Methods used in BuildStream       #
    #############################################################

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

    cpdef object _strip_node_info(self):
        raise NotImplementedError()

    #############################################################
    #                Abstract Protected Methods                 #
    #############################################################

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
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

    cdef bint _walk_find(self, Node target, list path) except *:
        raise NotImplementedError()

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    cdef bint _shares_position_with(self, Node target):
        return (self.file_index == target.file_index and
                self.line == target.line and
                self.column == target.column)


cdef class ScalarNode(Node):

    def __cinit__(self, int file_index, int line, int column, object value):
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

    #############################################################
    #                       Public Methods                      #
    #############################################################

    cpdef bint as_bool(self) except *:
        if type(self.value) is bool:
            return self.value

        # Don't coerce strings to booleans, this makes "False" strings evaluate to True
        if self.value in ('True', 'true'):
            return True
        elif self.value in ('False', 'false'):
            return False
        else:
            provenance = self.get_provenance()
            path = provenance._toplevel._find(self)[-1]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                "{}: Value of '{}' is not of the expected type '{}'"
                .format(provenance, path, bool.__name__, self.value))

    cpdef int as_int(self) except *:
        try:
            return int(self.value)
        except ValueError:
            provenance = self.get_provenance()
            path = provenance._toplevel._find(self)[-1]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                "{}: Value of '{}' is not of the expected type '{}'"
                .format(provenance, path, int.__name__))

    cpdef str as_str(self):
        # We keep 'None' as 'None' to simplify the API's usage and allow chaining for users
        if self.value is None:
            return None
        return str(self.value)

    cpdef bint is_none(self):
        return self.value is None

    #############################################################
    #               Public Methods implementations              #
    #############################################################

    cpdef ScalarNode copy(self):
        return self

    #############################################################
    #              Private Methods implementations              #
    #############################################################

    cpdef void _assert_fully_composited(self) except *:
        pass

    cpdef object _strip_node_info(self):
        return self.value

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        cdef Node target_value = target.value.get(key)

        if target_value is not None and type(target_value) is not ScalarNode:
            raise _CompositeError(path,
                                  "{}: Cannot compose scalar on non-scalar at {}".format(
                                    self.get_provenance(),
                                    target_value.get_provenance()))

        target.value[key] = self

    cdef bint _is_composite_list(self) except *:
        return False

    cdef bint _walk_find(self, Node target, list path) except *:
        return self._shares_position_with(target)


cdef class MappingNode(Node):

    def __cinit__(self, int file_index, int line, int column, dict value):
        self.value = value

    def __contains__(self, what):
        return what in self.value

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

    #############################################################
    #                       Public Methods                      #
    #############################################################

    cpdef bint get_bool(self, str key, object default=_sentinel) except *:
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_bool()

    cpdef int get_int(self, str key, object default=_sentinel) except *:
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_int()

    cpdef MappingNode get_mapping(self, str key, object default=_sentinel):
        value = self._get(key, default, MappingNode)

        if type(value) is not MappingNode and value is not None:
            provenance = value.get_provenance()
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type 'Mapping'"
                            .format(provenance, key))

        return value

    cpdef Node get_node(self, str key, list allowed_types = None, bint allow_none = False):
        cdef value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if allow_none:
                return None

            provenance = self.get_provenance()
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dictionary did not contain expected key '{}'".format(provenance, key))

        if allowed_types and type(value) not in allowed_types:
            provenance = self.get_provenance()
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not one of the following: {}.".format(
                                provenance, key, ", ".join(allowed_types)))

        return value

    cpdef ScalarNode get_scalar(self, str key, object default=_sentinel):
        value = self._get(key, default, ScalarNode)

        if type(value) is not ScalarNode:
            if value is None:
                value = ScalarNode.__new__(ScalarNode, self.file_index, 0, next_synthetic_counter(), None)
            else:
                provenance = value.get_provenance()
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Value of '{}' is not of the expected type 'Scalar'"
                                .format(provenance, key))

        return value

    cpdef SequenceNode get_sequence(self, str key, object default=_sentinel):
        value = self._get(key, default, SequenceNode)

        if type(value) is not SequenceNode and value is not None:
            provenance = value.get_provenance()
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type 'Sequence'"
                            .format(provenance, key))

        return value

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
                provenance = self.get_node(key).get_provenance()
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Unexpected key: {}".format(provenance, key))

    cpdef object values(self):
        return self.value.values()

    #############################################################
    #               Public Methods implementations              #
    #############################################################

    cpdef MappingNode copy(self):
        cdef dict copy = {}
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            copy[key] = value.copy()

        return MappingNode.__new__(MappingNode, self.file_index, self.line, self.column, copy)

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # _composite()
    #
    # Compose one mapping node onto another
    #
    # Args:
    #    target (Node): The target to compose into
    #
    # Raises: LoadError
    #
    cpdef void _composite(self, MappingNode target) except *:
        try:
            self.__composite(target, [])
        except _CompositeError as e:
            source_provenance = self.get_provenance()
            error_prefix = ""
            if source_provenance:
                error_prefix = "{}: ".format(source_provenance)
            raise LoadError(LoadErrorReason.ILLEGAL_COMPOSITE,
                            "{}Failure composing {}: {}"
                            .format(error_prefix,
                                    e.path,
                                    e.message)) from e

    # Like _composite(target, source), but where target overrides source instead.
    #
    cpdef void _composite_under(self, MappingNode target) except *:
        target._composite(self)

        cdef str key
        cdef Node value
        cdef list to_delete = [key for key in target.value.keys() if key not in self.value]

        for key, value in self.value.items():
            target.value[key] = value
        for key in to_delete:
            del target.value[key]

    # _find()
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

    #############################################################
    #              Private Methods implementations              #
    #############################################################

    cpdef void _assert_fully_composited(self) except *:
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            # Assert that list composition directives dont remain, this
            # indicates that the user intended to override a list which
            # never existed in the underlying data
            #
            if key in ('(>)', '(<)', '(=)'):
                provenance = value.get_provenance()
                raise LoadError(LoadErrorReason.TRAILING_LIST_DIRECTIVE,
                                "{}: Attempt to override non-existing list".format(provenance))

            value._assert_fully_composited()

    cpdef object _strip_node_info(self):
        cdef str key
        cdef Node value

        return {key: value._strip_node_info() for key, value in self.value.items()}

    #############################################################
    #                     Protected Methods                     #
    #############################################################

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
                    raise _CompositeError(path,
                                          "{}: Cannot compose lists onto {}".format(
                                             self.get_provenance(),
                                             target_value.get_provenance()))
        else:
            # We're composing a dict into target now
            if key not in target.value:
                # Target lacks a dict at that point, make a fresh one with
                # the same provenance as the incoming dict
                target.value[key] = MappingNode.__new__(MappingNode, self.file_index, self.line, self.column, {})

            self.__composite(target.value[key], path)

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

    cdef Node _get(self, str key, object default, object default_constructor):
        value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if default is _sentinel:
                provenance = self.get_provenance()
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Dictionary did not contain expected key '{}'".format(provenance, key))

            if default is None:
                value = None
            else:
                value = default_constructor.__new__(
                    default_constructor, _SYNTHETIC_FILE_INDEX, 0, next_synthetic_counter(), default)

        return value

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
            provenance = self.get_provenance()
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Dictionary contains array composition directives and arbitrary keys"
                            .format(provenance))

        return has_directives

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

    #############################################################
    #                      Private Methods                      #
    #############################################################

    cdef void __composite(self, MappingNode target, list path=None) except *:
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            path.append(key)
            value._compose_on(key, target, path)
            path.pop()


cdef class SequenceNode(Node):
    def __cinit__(self, int file_index, int line, int column, list value):
        self.value = value

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

    #############################################################
    #                       Public Methods                      #
    #############################################################

    cpdef void append(self, object value):
        if type(value) in [MappingNode, ScalarNode, SequenceNode]:
            self.value.append(value)
        else:
            node = _create_node_recursive(value, self)
            self.value.append(node)

    cpdef list as_str_list(self):
        return [node.as_str() for node in self.value]

    cpdef MappingNode mapping_at(self, int index):
        value = self.value[index]

        if type(value) is not MappingNode:
            provenance = self.get_provenance()
            path = ["[{}]".format(p) for p in provenance.toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, MappingNode.__name__))
        return value

    cpdef Node node_at(self, int index, list allowed_types = None):
        cdef value = self.value[index]

        if allowed_types and type(value) not in allowed_types:
            provenance = self.get_provenance()
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not one of the following: {}.".format(
                                provenance, index, ", ".join(allowed_types)))

        return value

    cpdef ScalarNode scalar_at(self, int index):
        value = self.value[index]

        if type(value) is not ScalarNode:
            provenance = self.get_provenance()
            path = ["[{}]".format(p) for p in provenance.toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, ScalarNode.__name__))
        return value

    cpdef SequenceNode sequence_at(self, int index):
        value = self.value[index]

        if type(value) is not SequenceNode:
            provenance = self.get_provenance()
            path = ["[{}]".format(p) for p in provenance.toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, SequenceNode.__name__))

        return value

    #############################################################
    #               Public Methods implementations              #
    #############################################################

    cpdef SequenceNode copy(self):
        cdef list copy = []
        cdef Node entry

        for entry in self.value:
            copy.append(entry.copy())

        return SequenceNode.__new__(SequenceNode, self.file_index, self.line, self.column, copy)

    #############################################################
    #              Private Methods implementations              #
    #############################################################

    cpdef void _assert_fully_composited(self) except *:
        cdef Node value
        for value in self.value:
            value._assert_fully_composited()

    cpdef object _strip_node_info(self):
        cdef Node value
        return [value._strip_node_info() for value in self.value]

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        # List clobbers anything list-like
        cdef Node target_value = target.value.get(key)

        if not (target_value is None or
                type(target_value) is SequenceNode or
                target_value._is_composite_list()):
            raise _CompositeError(path,
                                  "{}: List cannot overwrite {} at: {}"
                                  .format(self.get_provenance(),
                                          key,
                                          target_value.get_provenance()))
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


# Returned from Node.get_provenance
cdef class ProvenanceInformation:

    def __init__(self, Node nodeish):
        cdef _FileInfo fileinfo

        self._node = nodeish
        if (nodeish is None) or (nodeish.file_index == _SYNTHETIC_FILE_INDEX):
            self._filename = ""
            self._shortname = ""
            self._displayname = ""
            self._line = 1
            self._col = 0
            self._toplevel = None
            self._project = None
        else:
            fileinfo = <_FileInfo> _FILE_LIST[nodeish.file_index]
            self._filename = fileinfo.filename
            self._shortname = fileinfo.shortname
            self._displayname = fileinfo.displayname
            # We add 1 here to convert from computerish to humanish
            self._line = nodeish.line + 1
            self._col = nodeish.column
            self._toplevel = fileinfo.toplevel
            self._project = fileinfo.project
        self._is_synthetic = (self._filename == '') or (self._col < 0)

    # Convert a Provenance to a string for error reporting
    def __str__(self):
        if self._is_synthetic:
            return "{} [synthetic node]".format(self._displayname)
        else:
            return "{} [line {:d} column {:d}]".format(self._displayname, self._line, self._col)


# assert_symbol_name()
#
# A helper function to check if a loaded string is a valid symbol
# name and to raise a consistent LoadError if not. For strings which
# are required to be symbols.
#
# Args:
#    symbol_name (str): The loaded symbol name
#    purpose (str): The purpose of the string, for an error message
#    ref_node (Node): The node of the loaded symbol, or None
#    allow_dashes (bool): Whether dashes are allowed for this symbol
#
# Raises:
#    LoadError: If the symbol_name is invalid
#
# Note that dashes are generally preferred for variable names and
# usage in YAML, but things such as option names which will be
# evaluated with jinja2 cannot use dashes.
def assert_symbol_name(str symbol_name, str purpose, *, Node ref_node=None, bint allow_dashes=True):
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
        if ref_node:
            provenance = ref_node.get_provenance()
            if provenance is not None:
                message = "{}: {}".format(provenance, message)

        raise LoadError(LoadErrorReason.INVALID_SYMBOL_NAME,
                        message, detail=detail)


#############################################################
#                BuildStream Private methods                #
#############################################################
# Purely synthetic nodes will have _SYNTHETIC_FILE_INDEX for the file number, have line number
# zero, and a negative column number which comes from inverting the next value
# out of this counter.  Synthetic nodes created with a reference node will
# have a file number from the reference node, some unknown line number, and
# a negative column number from this counter.
cdef int _SYNTHETIC_FILE_INDEX = -1

# File name handling
cdef list _FILE_LIST = []


cdef Py_ssize_t _create_new_file(str filename, str shortname, str displayname, Node toplevel, object project):
    cdef Py_ssize_t file_number = len(_FILE_LIST)
    _FILE_LIST.append(_FileInfo(filename, shortname, displayname, None, project))

    return file_number


cdef void _set_root_node_for_file(Py_ssize_t file_index, MappingNode contents) except *:
    cdef _FileInfo f_info

    if file_index != _SYNTHETIC_FILE_INDEX:
        f_info = <_FileInfo> _FILE_LIST[file_index]
        f_info.toplevel = contents


# _new_synthetic_file()
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
def _new_synthetic_file(str filename, object project=None):
    cdef Py_ssize_t file_index = len(_FILE_LIST)
    cdef Node node = MappingNode.__new__(MappingNode, file_index, 0, 0, {})

    _FILE_LIST.append(_FileInfo(filename,
                       filename,
                       "<synthetic {}>".format(filename),
                       node,
                       project))
    return node


#############################################################
#                 Module local helper Methods               #
#############################################################

# synthetic counter for synthetic nodes
cdef int __counter = 0


class _CompositeError(Exception):
    def __init__(self, path, message):
        super().__init__(message)
        self.path = path
        self.message = message


# Metadata container for a yaml toplevel node.
#
# This class contains metadata around a yaml node in order to be able
# to trace back the provenance of a node to the file.
#
cdef class _FileInfo:

    cdef str filename, shortname, displayname
    cdef MappingNode toplevel,
    cdef object project

    def __init__(self, str filename, str shortname, str displayname, MappingNode toplevel, object project):
        self.filename = filename
        self.shortname = shortname
        self.displayname = displayname
        self.toplevel = toplevel
        self.project = project


cdef int next_synthetic_counter():
    global __counter
    __counter -= 1
    return __counter


cdef Node _create_node_recursive(object value, Node ref_node):
    cdef value_type = type(value)

    if value_type is list:
        node = _new_node_from_list(value, ref_node)
    elif value_type in [int, str, bool]:
        node = ScalarNode.__new__(ScalarNode, ref_node.file_index, ref_node.line, next_synthetic_counter(), value)
    elif value_type is dict:
        node = _new_node_from_dict(value, ref_node)
    else:
        raise ValueError(
            "Unable to assign a value of type {} to a Node.".format(value_type))

    return node


# _new_node_from_dict()
#
# Args:
#   indict (dict): The input dictionary
#   ref_node (Node): The dictionary to take as reference for position
#
# Returns:
#   (Node): A new synthetic YAML tree which represents this dictionary
#
cdef Node _new_node_from_dict(dict indict, Node ref_node):
    cdef MappingNode ret = MappingNode.__new__(
        MappingNode, ref_node.file_index, ref_node.line, next_synthetic_counter(), {})
    cdef str k

    for k, v in indict.items():
        ret.value[k] = _create_node_recursive(v, ref_node)

    return ret


# Internal function to help new_node_from_dict() to handle lists
cdef Node _new_node_from_list(list inlist, Node ref_node):
    cdef SequenceNode ret = SequenceNode.__new__(
        SequenceNode, ref_node.file_index, ref_node.line, next_synthetic_counter(), [])

    for v in inlist:
        ret.value.append(_create_node_recursive(v, ref_node))

    return ret
