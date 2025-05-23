#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Daniel Silverstone <daniel.silverstone@codethink.co.uk>
#        James Ennis <james.ennis@codethink.co.uk>
#        Benjamin Schubert <bschubert@bloomberg.net>

"""
Node - Parsed YAML configuration
================================

This module contains the building blocks for handling YAML configuration.

Everything that is loaded from YAML is encapsulated in such nodes, which
provide helper methods to validate configuration on access.

Using node methods when reading configuration will ensure that errors
are always coherently notified to the user.

.. note:: Plugins are not expected to handle exceptions thrown by node
          methods for the above reason; They are private. There should
          always be a way to acquire information without resorting to
          exception handling.

Node types
----------

The most important classes defined here are:

* :class:`.MappingNode`: represents a YAML Mapping (dictionary)
* :class:`.ScalarNode`: represents a YAML Scalar (string, boolean, integer)
* :class:`.SequenceNode`: represents a YAML Sequence (list)


Class Reference
---------------
"""

import string

from ._exceptions import LoadError
from .exceptions import LoadErrorReason


# A sentinel to be used as a default argument for functions that need
# to distinguish between a kwarg set to None and an unset kwarg.
_sentinel = object()


cdef class Node:
    """This is the base class for YAML document nodes.

    YAML Nodes contain information to describe the provenance of the YAML
    which resulted in the Node, allowing mapping back from a Node to the place
    in the file it came from.

    .. note:: You should never need to create a :class:`.Node` manually.
              If you do, you can create :class:`.Node` from dictionaries with
              :func:`Node.from_dict() <buildstream.node.Node.from_dict>`.
              If something else is needed, please open an issue.
    """

    def __init__(self):
        raise NotImplementedError("Please do not construct nodes like this. Use Node.from_dict(dict) instead.")

    def __cinit__(self, int file_index, int line, int column, *args):
        self.file_index = file_index
        self.line = line
        self.column = column

    # This is in order to ensure we never add a `Node` to a cache key
    # as ujson will try to convert objects if they have a `__json__`
    # attribute.
    def __json__(self):
        raise ValueError("Nodes should not be allowed when jsonify-ing data", self)

    def __str__(self):
        return "{}: {}".format(self.get_provenance(), self.strip_node_info())

    #############################################################
    #                  Abstract Public Methods                  #
    #############################################################

    cpdef Node clone(self):
        """Clone the node and return the copy.

        Returns:
            :class:`.Node`: a clone of the current node
        """
        raise NotImplementedError()

    cpdef object strip_node_info(self):
        """ Remove all the node information (provenance) and return the underlying data as plain python objects

        Returns:
            (list, dict, str, None): the underlying data that was held in the node structure.
        """
        raise NotImplementedError()

    #############################################################
    #                       Public Methods                      #
    #############################################################

    @classmethod
    def from_dict(cls, dict value):
        """from_dict(value)

        Create a new node from the given dictionary.

        This is a recursive operation, and will transform every value in the
        dictionary to a :class:`.Node` instance

        Valid values for keys are `str`
        Valid values for values are `list`, `dict`, `str`, `int`, `bool` or None.
        `list` and `dict` can also only contain such types.

        Args:
            value (dict): dictionary from which to create a node.

        Raises:
            :class:`TypeError`: when the value cannot be converted to a :class:`Node`

        Returns:
            :class:`.MappingNode`: a new mapping containing the value
        """
        if value:
            return __new_node_from_dict(value, MappingNode.__new__(
                MappingNode, _SYNTHETIC_FILE_INDEX, 0, __next_synthetic_counter(), {}))
        else:
            # We got an empty dict, we can shortcut
            return MappingNode.__new__(MappingNode, _SYNTHETIC_FILE_INDEX, 0, __next_synthetic_counter(), {})

    cpdef ProvenanceInformation get_provenance(self):
        """A convenience accessor to obtain the node's :class:`.ProvenanceInformation`

        The provenance information allows you to inform the user of where
        a node came. Transforming the information to a string will show the file, line and column
        in the file where the node is.

        An example usage would be:

        .. code-block:: python

            # With `config` being your node
            max_jobs_node = config.get_node('max-jobs')
            max_jobs = max_jobs_node.as_int()

            if max_jobs < 1:  # We can't get a negative number of jobs
                raise LoadError("Error at {}: Max jobs needs to be >= 1".format(
                    max_jobs_node.get_provenance()
                )

            # Will print something like:
            # element.bst [line 4, col 7]: Max jobs needs to be >= 1

        Returns:
            :class:`.ProvenanceInformation`: the provenance information for the node.
        """
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

    #############################################################
    #                Abstract Protected Methods                 #
    #############################################################

    # _compose_on(key, target, path)
    #
    # Compose the current node on the given target.
    #
    # Args:
    #   key (str): key on the target on which to compose the current value
    #   target (.Node): target node on which to compose
    #   path (list): path from the root of the target when composing recursively
    #         in order to give accurate error reporting.
    #
    # Raises:
    #   (_CompositeError): if an error is encountered during composition
    #
    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        raise NotImplementedError()

    # _is_composite_list
    #
    # Checks if the node is a Mapping with list composition
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

    # _walk_find(target, path)
    #
    # Walk the node to search for `target`.
    #
    # When this returns `True`, the `path` argument will contain the full path
    # to the target from the root node.
    #
    # Args:
    #   target (.Node): target to find in the node tree
    #   path (list): current path from the root
    #
    # Returns:
    #   (bool): whether the target was found in the tree or not
    #
    cdef bint _walk_find(self, Node target, list path) except *:
        raise NotImplementedError()

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    # _shares_position_with(target)
    #
    # Check whether the current node is at the same position in its tree as the target.
    #
    # This is useful when we want to know if two nodes are 'identical', that is they
    # are at the exact same position in each respective tree, but do not necessarily
    # have the same content.
    #
    # Args:
    #   target (.Node): the target to compare with the current node.
    #
    # Returns:
    #   (bool): whether the two nodes share the same position
    #
    cdef bint _shares_position_with(self, Node target):
        return (self.file_index == target.file_index and
                self.line == target.line and
                self.column == target.column)


cdef class ScalarNode(Node):
    """This class represents a Scalar (int, str, bool, None) in a YAML document.

    .. note:: If you need to store another type of scalars, please open an issue
              on the project.

    .. note:: You should never have to create a :class:`.ScalarNode` directly
    """

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

    def __reduce__(self):
        return (
            ScalarNode.__new__,
            (ScalarNode, self.file_index, self.line, self.column, self.value),
        )

    #############################################################
    #                       Public Methods                      #
    #############################################################

    cpdef bint as_bool(self) except *:
        """Get the value of the node as a boolean.

        .. note:: BuildStream treats the values 'True', 'true' and '1' as True,
                  and the values 'False', 'false' and '0' as False.  Any other
                  string values (such as the valid YAML 'TRUE' or 'FALSE'
                  will be considered as an error)

        Raises:
            :class:`buildstream._exceptions.LoadError`: if the value cannot be coerced to
                                                        a bool correctly.

        Returns:
            :class:`bool`: the value contained in the node, as a boolean
        """
        if type(self.value) is bool:
            return self.value

        # Don't coerce strings to booleans, this makes "False" strings evaluate to True
        if self.value in ('True', 'true', '1'):
            return True
        elif self.value in ('False', 'false', '0'):
            return False
        else:
            provenance = self.get_provenance()
            path = provenance._toplevel._find(self)[-1]
            raise LoadError("{}: Value of '{}' is not of the expected type 'boolean'"
                            .format(provenance, path),
                            LoadErrorReason.INVALID_DATA)

    cpdef object as_enum(self, object constraint):
        """Get the value of the node as an enum member from `constraint`

        The constraint must be a :class:`buildstream.types.FastEnum` or a plain python Enum.

        For example you could do:

        .. code-block:: python

            from buildstream.types import FastEnum

            class SupportedCompressions(FastEnum):
              NONE = "none"
              GZIP = "gzip"
              XZ = "xz"


            x = config.get_scalar('compress').as_enum(SupportedCompressions)

            if x == SupportedCompressions.GZIP:
                print("Using GZIP")

        Args:
            constraint (:class:`buildstream.types.FastEnum` or :class:`Enum`): an enum from which to extract the value
                                                                               for the current node.

        Returns:
            :class:`FastEnum` or :class:`Enum`: the value contained in the node, as a member of `constraint`
        """
        try:
            return constraint(self.value)
        except ValueError:
            provenance = self.get_provenance()
            path = provenance._toplevel._find(self)[-1]
            valid_values = [str(v.value) for v in constraint]
            raise LoadError("{}: Value of '{}' should be one of '{}'".format(
                                provenance, path, ", ".join(valid_values)),
                            LoadErrorReason.INVALID_DATA)

    cpdef int as_int(self) except *:
        """Get the value of the node as an integer.

        Raises:
            :class:`buildstream._exceptions.LoadError`: if the value cannot be coerced to
                                                        an integer correctly.

        Returns:
            :class:`int`: the value contained in the node, as a integer
        """
        try:
            return int(self.value)
        except ValueError:
            provenance = self.get_provenance()
            path = provenance._toplevel._find(self)[-1]
            raise LoadError("{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, int.__name__),
                            LoadErrorReason.INVALID_DATA)

    cpdef str as_str(self):
        """Get the value of the node as a string.

        Returns:
            :class:`str`: the value contained in the node, as a string, or `None` if the content
                          is `None`.
        """
        # We keep 'None' as 'None' to simplify the API's usage and allow chaining for users
        if self.value is None:
            return None
        return str(self.value)

    cpdef bint is_none(self):
        """Determine whether the current scalar is `None`.

        Returns:
            :class:`bool`: `True` if the value of the scalar is `None`, else `False`
        """
        return self.value is None

    #############################################################
    #               Public Methods implementations              #
    #############################################################

    cpdef ScalarNode clone(self):
        return ScalarNode.__new__(
            ScalarNode, self.file_index, self.line, self.column, self.value
        )

    cpdef object strip_node_info(self):
        return self.value

    #############################################################
    #              Private Methods implementations              #
    #############################################################

    cpdef void _assert_fully_composited(self) except *:
        pass

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        cdef Node target_value = target.value.get(key)

        if target_value is not None and type(target_value) is not ScalarNode:
            raise __CompositeError(path,
                                   "{}: Cannot compose scalar on non-scalar at {}".format(
                                       self.get_provenance(),
                                       target_value.get_provenance()))

        target.value[key] = self.clone()

    cdef bint _is_composite_list(self) except *:
        return False

    cdef bint _walk_find(self, Node target, list path) except *:
        return self._shares_position_with(target)


cdef class MappingNode(Node):
    """This class represents a Mapping (dict) in a YAML document.

    It behaves mostly like a :class:`dict`, but doesn't allow untyped value access
    (Nothing of the form :code:`my_dict[my_value]`.

    It also doesn't allow anything else than :class:`str` as keys, to align with YAML.

    You can however use common dict operations in it:

    .. code-block:: python

        # Assign a new value to a key
        my_mapping[key] = my_value

        # Delete an entry
        del my_mapping[key]

    When assigning a key/value pair, the key must be a string,
    and the value can be any of:

    * a :class:`Node`, in which case the node is just assigned like normally
    * a :class:`list`, :class:`dict`, :class:`int`, :class:`str`, :class:`bool` or :class:`None`.
      In which case, the value will be converted to a :class:`Node` for you.

    Therefore, all values in a :class:`.MappingNode` will be :class:`Node`.

    .. note:: You should never create an instance directly. Use :func:`Node.from_dict() <buildstream.node.Node.from_dict>`
              instead, which will ensure your node is correctly formatted.
    """

    def __cinit__(self, int file_index, int line, int column, dict value):
        self.value = value

    def __reduce__(self):
        return (
            MappingNode.__new__,
            (MappingNode, self.file_index, self.line, self.column, self.value),
        )

    def __contains__(self, what):
        return what in self.value

    def __delitem__(self, str key):
        del self.value[key]

    def __setitem__(self, str key, object value):
        cdef Node old_value

        if type(value) in [MappingNode, ScalarNode, SequenceNode]:
            self.value[key] = value
        else:
            node = __create_node_recursive(value, self)

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
        """get_bool(key, default=sentinel)

        Get the value of the node for `key` as a boolean.

        This is equivalent to: :code:`mapping.get_scalar(my_key, my_default).as_bool()`.

        Args:
            key (str): key for which to get the value
            default (bool): default value to return if `key` is not in the mapping

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.ScalarNode` or isn't a
                                                       valid `boolean`

        Returns:
            :class:`bool`: the value at `key` or the default
        """
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_bool()

    cpdef object get_enum(self, str key, object constraint, object default=_sentinel):
        """Get the value of the node as an enum member from `constraint`

        Args:
            key (str): key for which to get the value
            constraint (:class:`buildstream.types.FastEnum` or :class:`Enum`): an enum from which to extract the value
                                                                               for the current node.
            default (object): default value to return if `key` is not in the mapping

        Raises:
            :class:`buildstream._exceptions.LoadError`: if the value is not is not found or not part of the
                                                        provided enum.

        Returns:
            :class:`buildstream.types.Enum` or :class:`Enum`: the value contained in the node, as a member of
                                                              `constraint`
        """
        cdef object value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if default is _sentinel:
                provenance = self.get_provenance()
                raise LoadError("{}: Dictionary did not contain expected key '{}'".format(provenance, key),
                                LoadErrorReason.INVALID_DATA)

            if default is None:
                return None
            else:
                return constraint(default)

        if type(value) is not ScalarNode:
            provenance = value.get_provenance()
            raise LoadError("{}: Value of '{}' is not of the expected type 'scalar'"
                                .format(provenance, key),
                            LoadErrorReason.INVALID_DATA)

        return (<ScalarNode> value).as_enum(constraint)

    cpdef object get_int(self, str key, object default=_sentinel):
        """get_int(key, default=sentinel)

        Get the value of the node for `key` as an integer.

        This is equivalent to: :code:`mapping.get_scalar(my_key, my_default).as_int()`.

        Args:
            key (str): key for which to get the value
            default (int, None): default value to return if `key` is not in the mapping

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.ScalarNode` or isn't a
                                                       valid `integer`

        Returns:
            :class:`int` or :class:`None`: the value at `key` or the default
        """
        cdef ScalarNode scalar = self.get_scalar(key, default)
        if default is None and scalar.is_none():
            return None
        return scalar.as_int()

    cpdef MappingNode get_mapping(self, str key, object default=_sentinel):
        """get_mapping(key, default=sentinel)

        Get the value of the node for `key` as a :class:`.MappingNode`.

        Args:
            key (str): key for which to get the value
            default (dict): default value to return if `key` is not in the mapping. It will be converted
                            to a :class:`.MappingNode` before being returned

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.MappingNode`

        Returns:
            :class:`.MappingNode`: the value at `key` or the default
        """
        value = self._get(key, default, MappingNode)

        if type(value) is not MappingNode and value is not None:
            provenance = value.get_provenance()
            raise LoadError("{}: Value of '{}' is not of the expected type 'dict'"
                            .format(provenance, key), LoadErrorReason.INVALID_DATA)

        return value

    cpdef Node get_node(self, str key, list allowed_types = None, bint allow_none = False):
        """get_node(key, allowed_types=None, allow_none=False)

        Get the value of the node for `key` as a :class:`.Node`.

        This is useful if you have configuration that can be either a :class:`.ScalarNode` or
        a :class:`.MappingNode` for example.

        This method will validate that the value is indeed exactly one of those types (not a subclass)
        and raise an exception accordingly.

        Args:
            key (str): key for which to get the value
            allowed_types (list): list of valid subtypes of :class:`.Node` that are valid return values.
                                  If this is `None`, no checks are done on the return value.
            allow_none (bool): whether to allow the return value to be `None` or not

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not one
                                                       of the expected types or if it doesn't
                                                       exist.

        Returns:
            :class:`.Node`: the value at `key` or `None`
        """
        cdef value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if allow_none:
                return None

            provenance = self.get_provenance()
            raise LoadError("{}: Dictionary did not contain expected key '{}'".format(provenance, key),
                            LoadErrorReason.INVALID_DATA)

        __validate_node_type(value, allowed_types, key)

        return value

    cpdef ScalarNode get_scalar(self, str key, object default=_sentinel):
        """get_scalar(key, default=sentinel)

        Get the value of the node for `key` as a :class:`.ScalarNode`.

        Args:
            key (str): key for which to get the value
            default (str, int, bool, None): default value to return if `key` is not in the mapping.
                                            It will be converted to a :class:`.ScalarNode` before being
                                            returned.

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.MappingNode`

        Returns:
            :class:`.ScalarNode`: the value at `key` or the default
        """
        value = self._get(key, default, ScalarNode)

        if type(value) is not ScalarNode:
            if value is None:
                value = ScalarNode.__new__(ScalarNode, self.file_index, 0, __next_synthetic_counter(), None)
            else:
                provenance = value.get_provenance()
                raise LoadError("{}: Value of '{}' is not of the expected type 'scalar'"
                                .format(provenance, key), LoadErrorReason.INVALID_DATA)

        return value

    cpdef SequenceNode get_sequence(self, str key, object default=_sentinel, list allowed_types = None):
        """get_sequence(key, default=sentinel)

        Get the value of the node for `key` as a :class:`.SequenceNode`.

        Args:
            key (str): key for which to get the value
            default (list): default value to return if `key` is not in the mapping. It will be converted
                            to a :class:`.SequenceNode` before being returned
            allowed_types (list): list of valid subtypes of :class:`.Node` that are valid for nodes in the sequence.

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.SequenceNode`

        Returns:
            :class:`.SequenceNode`: the value at `key` or the default
        """
        cdef Node value = self._get(key, default, SequenceNode)
        cdef Node node

        if type(value) is not SequenceNode and value is not None:
            provenance = value.get_provenance()
            raise LoadError("{}: Value of '{}' is not of the expected type 'list'"
                            .format(provenance, key), LoadErrorReason.INVALID_DATA)

        if allowed_types:
            for node in value:
                __validate_node_type(node, allowed_types)

        return <SequenceNode> value

    cpdef str get_str(self, str key, object default=_sentinel):
        """get_str(key, default=sentinel)

        Get the value of the node for `key` as an string.

        This is equivalent to: :code:`mapping.get_scalar(my_key, my_default).as_str()`.

        Args:
            key (str): key for which to get the value
            default (str): default value to return if `key` is not in the mapping

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.ScalarNode` or isn't a
                                                       valid `str`

        Returns:
            :class:`str`: the value at `key` or the default
        """
        cdef ScalarNode scalar = self.get_scalar(key, default)
        return scalar.as_str()

    cpdef list get_str_list(self, str key, object default=_sentinel):
        """get_str_list(key, default=sentinel)

        Get the value of the node for `key` as a list of strings.

        This is equivalent to: :code:`mapping.get_sequence(my_key, my_default).as_str_list()`.

        Args:
            key (str): key for which to get the value
            default (str): default value to return if `key` is not in the mapping

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.SequenceNode` or if any
                                                       of its internal values is not a ScalarNode.

        Returns:
            :class:`list`: the value at `key` or the default
        """
        cdef SequenceNode sequence = self.get_sequence(key, default)
        if sequence is not None:
            return sequence.as_str_list()
        return None

    cpdef object items(self):
        """Get a new view of the mapping items ((key, value) pairs).

        This is equivalent to running :code:`my_dict.item()` on a `dict`.

        Returns:
             :class:`dict_items`: a view on the underlying dictionary
        """
        return self.value.items()

    cpdef list keys(self):
        """Get the list of all keys in the mapping.

        This is equivalent to running :code:`my_dict.keys()` on a `dict`.

        Returns:
             :class:`list`: a list of all keys in the mapping
        """
        return list(self.value.keys())

    cpdef void safe_del(self, str key):
        """safe_del(key)

        Remove the entry at `key` in the dictionary if it exists.

        This method is a safe equivalent to :code:`del mapping[key]`, that doesn't
        throw anything if the key doesn't exist.

        Args:
            key (str): key to remove from the mapping
        """
        self.value.pop(key, None)

    cpdef void validate_keys(self, list valid_keys) except *:
        """validate_keys(valid_keys)

        Validate that the node doesn't contain extra keys

        This validates the node so as to ensure the user has not specified
        any keys which are unrecognized by BuildStream (usually this
        means a typo which would otherwise not trigger an error).

        Args:
           valid_keys (list): A list of valid keys for the specified node

        Raises:
            :class:`buildstream._exceptions.LoadError`: In the case that the specified node contained
                                                        one or more invalid keys
        """

        # Probably the fastest way to do this: https://stackoverflow.com/a/23062482
        cdef set valid_keys_set = set(valid_keys)
        cdef str key

        for key in self.value:
            if key not in valid_keys_set:
                provenance = self.get_node(key).get_provenance()
                raise LoadError("{}: Unexpected key: {}".format(provenance, key),
                                LoadErrorReason.INVALID_DATA)

    cpdef object values(self):
        """Get the values in the mapping.

        This is equivalent to running :code:`my_dict.values()` on a `dict`.

        Returns:
             :class:`dict_values`: a list of all values in the mapping
        """
        return self.value.values()

    #############################################################
    #               Public Methods implementations              #
    #############################################################

    cpdef MappingNode clone(self):
        cdef dict copy = {}
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            copy[key] = value.clone()

        return MappingNode.__new__(MappingNode, self.file_index, self.line, self.column, copy)

    cpdef object strip_node_info(self):
        cdef str key
        cdef Node value

        return {key: value.strip_node_info() for key, value in self.value.items()}

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
        except __CompositeError as e:
            source_provenance = self.get_provenance()
            error_prefix = ""
            if source_provenance:
                error_prefix = "{}: ".format(source_provenance)
            raise LoadError("{}Failure composing {}: {}"
                            .format(error_prefix,
                                    e.path,
                                    e.message),
                            LoadErrorReason.ILLEGAL_COMPOSITE) from e

    # Like self._composite(target), but where values in the target don't get overridden by values in self.
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
                raise LoadError("{}: Attempt to override non-existing list".format(provenance),
                                LoadErrorReason.TRAILING_LIST_DIRECTIVE)

            value._assert_fully_composited()

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        cdef Node target_value

        if self._is_composite_list():
            if key not in target.value:
                # Composite list clobbers empty space
                target.value[key] = self.clone()
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
                    raise __CompositeError(path,
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

    # _compose_on_list(target)
    #
    # Compose the current node on the given sequence.
    #
    # Args:
    #   target (.SequenceNode): sequence on which to compose the current composite dict
    #
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

    # _compose_on_composite_dict(target)
    #
    # Compose the current node on the given composite dict.
    #
    # A composite dict is a dict that contains composition directives.
    #
    # Args:
    #   target (.MappingNode): sequence on which to compose the current composite dict
    #
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
            if key in ["(>)", "(<)", "(=)"]:
                has_directives = True
            else:
                has_keys = True

        if has_keys and has_directives:
            provenance = self.get_provenance()
            raise LoadError("{}: Dictionary contains list composition directives and arbitrary keys"
                            .format(provenance), LoadErrorReason.INVALID_DATA)

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

    # __composite(target, path)
    #
    # Helper method to compose the current node on another.
    #
    # Args:
    #   target (.MappingNode): target on which to compose the current node
    #   path (list): path from the root of the target when composing recursively
    #                in order to give accurate error reporting.
    #
    cdef void __composite(self, MappingNode target, list path) except *:
        cdef str key
        cdef Node value

        for key, value in self.value.items():
            path.append(key)
            value._compose_on(key, target, path)
            path.pop()

        # Clobber the provenance of the target mapping node if we're not
        # synthetic.
        if self.file_index != _SYNTHETIC_FILE_INDEX:
            target.file_index = self.file_index
            target.line = self.line
            target.column = self.column

    # _get(key, default, default_constructor)
    #
    # Internal helper method to get an entry from the underlying dictionary.
    #
    # Args:
    #   key (str): the key for which to retrieve the entry
    #   default (object): default value if the entry is not present
    #   default_constructor (object): method to transform the `default` into a Node
    #                                 if the entry is not present
    #
    # Raises:
    #   (LoadError): if the key is not present and no default has been given.
    #
    cdef Node _get(self, str key, object default, object default_constructor):
        value = self.value.get(key, _sentinel)

        if value is _sentinel:
            if default is _sentinel:
                provenance = self.get_provenance()
                raise LoadError("{}: Dictionary did not contain expected key '{}'".format(provenance, key),
                                LoadErrorReason.INVALID_DATA)

            if default is None:
                value = None
            else:
                value = default_constructor.__new__(
                    default_constructor, _SYNTHETIC_FILE_INDEX, 0, __next_synthetic_counter(), default)

        return value


cdef class SequenceNode(Node):
    """This class represents a Sequence (list) in a YAML document.

    It behaves mostly like a :class:`list`, but doesn't allow untyped value access
    (Nothing of the form :code:`my_list[my_value]`).

    You can however perform common list operations on it:

    .. code-block:: python

        # Assign a value
        my_sequence[key] = value

        # Get the length
        len(my_sequence)

        # Reverse it
        reversed(my_sequence)

        # And iter over it
        for value in my_sequence:
            print(value)

    All values in a :class:`SequenceNode` will be :class:`Node`.
    """

    def __cinit__(self, int file_index, int line, int column, list value):
        self.value = value

    def __reduce__(self):
        return (
            SequenceNode.__new__,
            (SequenceNode, self.file_index, self.line, self.column, self.value),
        )

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
            node = __create_node_recursive(value, self)

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
        """append(value)

        Append the given object to the sequence.

        Args:
            value (object): the value to append to the list. This can either be:

                                - a :class:`Node`
                                - a :class:`int`, :class:`bool`, :class:`str`, :class:`None`,
                                  :class:`dict` or :class:`list`. In which case, this will be
                                  converted into a :class:`Node` beforehand

        Raises:
            :class:`TypeError`: when the value cannot be converted to a :class:`Node`
        """
        if type(value) in [MappingNode, ScalarNode, SequenceNode]:
            self.value.append(value)
        else:
            node = __create_node_recursive(value, self)
            self.value.append(node)

    cpdef list as_str_list(self):
        """Get the values of the sequence as a list of strings.

        Raises:
            :class:`buildstream._exceptions.LoadError`: if the sequence contains more than
                                                        :class:`ScalarNode`

        Returns:
            :class:`list`: the content of the sequence as a list of strings
        """
        cdef list str_list = []
        cdef Node node
        for node in self.value:
            if type(node) is not ScalarNode:
                provenance = node.get_provenance()
                raise LoadError("{}: List item is not of the expected type 'scalar'"
                                .format(provenance), LoadErrorReason.INVALID_DATA)
            str_list.append(node.as_str())

        return str_list

    cpdef MappingNode mapping_at(self, int index):
        """mapping_at(index)

        Retrieve the entry at `index` as a :class:`.MappingNode`.

        Args:
            index (int): index for which to get the value

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.MappingNode`
           :class:`IndexError`: if no value exists at this index

        Returns:
            :class:`.MappingNode`: the value at `index`
        """
        value = self.value[index]

        if type(value) is not MappingNode:
            provenance = self.get_provenance()
            path = ["[{}]".format(p) for p in provenance._toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError("{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, MappingNode.__name__),
                            LoadErrorReason.INVALID_DATA)
        return value

    cpdef Node node_at(self, int index, list allowed_types = None):
        """node_at(index, allowed_types=None)

        Retrieve the entry at `index` as a :class:`.Node`.

        This is useful if you have configuration that can be either a :class:`.ScalarNode` or
        a :class:`.MappingNode` for example.

        This method will validate that the value is indeed exactly one of those types (not a subclass)
        and raise an exception accordingly.

        Args:
            index (int): index for which to get the value
            allowed_types (list): list of valid subtypes of :class:`.Node` that are valid return values.
                                  If this is `None`, no checks are done on the return value.

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `index` is not of one of the
                                                       expected types
           :class:`IndexError`: if no value exists at this index

        Returns:
            :class:`.Node`: the value at `index`
        """
        cdef value = self.value[index]
        __validate_node_type(value, allowed_types, str(index))
        return value

    cpdef ScalarNode scalar_at(self, int index):
        """scalar_at(index)

        Retrieve the entry at `index` as a :class:`.ScalarNode`.

        Args:
            index (int): index for which to get the value

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.ScalarNode`
           :class:`IndexError`: if no value exists at this index

        Returns:
            :class:`.ScalarNode`: the value at `index`
        """
        value = self.value[index]

        if type(value) is not ScalarNode:
            provenance = self.get_provenance()
            path = ["[{}]".format(p) for p in provenance._toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError("{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, ScalarNode.__name__),
                            LoadErrorReason.INVALID_DATA)
        return value

    cpdef SequenceNode sequence_at(self, int index):
        """sequence_at(index)

        Retrieve the entry at `index` as a :class:`.SequenceNode`.

        Args:
            index (int): index for which to get the value

        Raises:
           :class:`buildstream._exceptions.LoadError`: if the value at `key` is not a
                                                       :class:`.SequenceNode`
           :class:`IndexError`: if no value exists at this index

        Returns:
            :class:`.SequenceNode`: the value at `index`
        """
        value = self.value[index]

        if type(value) is not SequenceNode:
            provenance = self.get_provenance()
            path = ["[{}]".format(p) for p in provenance.toplevel._find(self)] + ["[{}]".format(index)]
            raise LoadError("{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, SequenceNode.__name__),
                            LoadErrorReason.INVALID_DATA)

        return value

    #############################################################
    #               Public Methods implementations              #
    #############################################################

    cpdef SequenceNode clone(self):
        cdef list copy = []
        cdef Node entry

        for entry in self.value:
            copy.append(entry.clone())

        return SequenceNode.__new__(SequenceNode, self.file_index, self.line, self.column, copy)

    cpdef object strip_node_info(self):
        cdef Node value
        return [value.strip_node_info() for value in self.value]

    #############################################################
    #              Private Methods implementations              #
    #############################################################

    cpdef void _assert_fully_composited(self) except *:
        cdef Node value
        for value in self.value:
            value._assert_fully_composited()

    #############################################################
    #                     Protected Methods                     #
    #############################################################

    cdef void _compose_on(self, str key, MappingNode target, list path) except *:
        # List clobbers anything list-like
        cdef Node target_value = target.value.get(key)

        if not (target_value is None or
                type(target_value) is SequenceNode or
                target_value._is_composite_list()):
            raise __CompositeError(path,
                                  "{}: List cannot overwrite {} at: {}"
                                  .format(self.get_provenance(),
                                          key,
                                          target_value.get_provenance()))

        # If the target is a list of conditional statements, then we are
        # also conditional statements, and we need to append ourselves
        # to that list instead of overwriting it in order to preserve the
        # conditional for later evaluation.
        if type(target_value) is SequenceNode and key == "(?)":
            (<SequenceNode> target.value[key]).value.extend(self.value)
        else:
            # Looks good, clobber it
            target.value[key] = self.clone()

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
    """Represents the location of a YAML node in a file.

    This can effectively be used as a pretty print to display those information in
    errors consistently.

    You can retrieve this information for a :class:`Node` with
    :func:`Node.get_provenance() <buildstream.node.Node.get_provenance()>`
    """

    def __init__(self, Node nodeish):
        cdef __FileInfo fileinfo

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
            fileinfo = <__FileInfo> __FILE_LIST[nodeish.file_index]
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


#############################################################
#                BuildStream Private methods                #
#############################################################

# Purely synthetic nodes will have _SYNTHETIC_FILE_INDEX for the file number, have line number
# zero, and a negative column number which comes from inverting the next value
# out of this counter.  Synthetic nodes created with a reference node will
# have a file number from the reference node, some unknown line number, and
# a negative column number from this counter.
cdef int _SYNTHETIC_FILE_INDEX = -1

# _assert_symbol_name()
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
def _assert_symbol_name(str symbol_name, str purpose, *, Node ref_node=None, bint allow_dashes=True):
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

        raise LoadError(message, LoadErrorReason.INVALID_SYMBOL_NAME, detail=detail)


# _create_new_file(filename, shortname, displayname, toplevel, project)
#
# Create a new synthetic file and return it's index in the `._FILE_LIST`.
#
# Args:
#   filename (str): the name to give to the file
#   shortname (str): a shorter name used when showing information on the screen
#   displayname (str): the name to give when reporting errors
#   project (object): project with which to associate the current file (when dealing with junctions)
#
# Returns:
#   (int): the index in the `._FILE_LIST` that identifies the new file
#
cdef Py_ssize_t _create_new_file(str filename, str shortname, str displayname, object project):
    cdef Py_ssize_t file_number = len(__FILE_LIST)
    __FILE_LIST.append(__FileInfo(filename, shortname, displayname, None, project))

    return file_number


# _set_root_node_for_file(file_index, contents)
#
# Set the root node for the given file
#
# Args:
#   file_index (int): the index in the `._FILE_LIST` for the file for which to set the root
#   contents (.MappingNode): node that should be the root for the file
#
cdef void _set_root_node_for_file(Py_ssize_t file_index, MappingNode contents) except *:
    cdef __FileInfo f_info

    if file_index != _SYNTHETIC_FILE_INDEX:
        f_info = <__FileInfo> __FILE_LIST[file_index]
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
    cdef Py_ssize_t file_index = len(__FILE_LIST)
    cdef Node node = MappingNode.__new__(MappingNode, file_index, 0, 0, {})

    __FILE_LIST.append(__FileInfo(filename,
                                  filename,
                                  "<synthetic {}>".format(filename),
                                  node,
                                  project))
    return node


# _reset_global_state()
#
# This resets the global variables __FILE_LIST and __counter to their initial
# state. This is used by the test suite to improve isolation between tests
# running in the same process.
#
def _reset_global_state():
    global __FILE_LIST, __counter
    __FILE_LIST = []
    __counter = 0


#############################################################
#                 Module local helper Methods               #
#############################################################

# File name handling
cdef list __FILE_LIST = []

# synthetic counter for synthetic nodes
cdef int __counter = 0


class __CompositeError(Exception):
    def __init__(self, path, message):
        super().__init__(message)
        self.path = path
        self.message = message


# Metadata container for a yaml toplevel node.
#
# This class contains metadata around a yaml node in order to be able
# to trace back the provenance of a node to the file.
#
cdef class __FileInfo:

    cdef str filename, shortname, displayname
    cdef MappingNode toplevel,
    cdef object project

    def __init__(self, str filename, str shortname, str displayname, MappingNode toplevel, object project):
        self.filename = filename
        self.shortname = shortname
        self.displayname = displayname
        self.toplevel = toplevel
        self.project = project


cdef int __next_synthetic_counter():
    global __counter
    __counter -= 1
    return __counter


cdef Node __create_node_recursive(object value, Node ref_node):
    cdef value_type = type(value)

    if value_type is list:
        node = __new_node_from_list(value, ref_node)
    elif value_type in [int, str, bool, type(None)]:
        node = ScalarNode.__new__(ScalarNode, ref_node.file_index, ref_node.line, __next_synthetic_counter(), value)
    elif value_type is dict:
        node = __new_node_from_dict(value, ref_node)
    else:
        raise TypeError(
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
cdef Node __new_node_from_dict(dict indict, Node ref_node):
    cdef MappingNode ret = MappingNode.__new__(
        MappingNode, ref_node.file_index, ref_node.line, __next_synthetic_counter(), {})
    cdef str k

    for k, v in indict.items():
        ret.value[k] = __create_node_recursive(v, ref_node)

    return ret


# Internal function to help new_node_from_dict() to handle lists
cdef Node __new_node_from_list(list inlist, Node ref_node):
    cdef SequenceNode ret = SequenceNode.__new__(
        SequenceNode, ref_node.file_index, ref_node.line, __next_synthetic_counter(), [])

    for v in inlist:
        ret.value.append(__create_node_recursive(v, ref_node))

    return ret


# __validate_node_type(node, allowed_types, key)
#
# Validates that this node is of the expected node type,
# and raises a user facing LoadError if not.
#
# Args:
#   allowed_types (list): list of valid subtypes of Node, or None
#   key (str): A key, in case the validated node is a value for a key
#
# Raises:
#    (LoadError): If this node is not of the expected type
#
cdef void __validate_node_type(Node node, list allowed_types = None, str key = None) except *:
    cdef ProvenanceInformation provenance
    cdef list human_types
    cdef str message

    if allowed_types and type(node) not in allowed_types:
        provenance = node.get_provenance()
        human_types = []
        if MappingNode in allowed_types:
            human_types.append("dict")
        if SequenceNode in allowed_types:
            human_types.append('list')
        if ScalarNode in allowed_types:
            human_types.append('scalar')

        message = "{}: Value ".format(provenance)
        if key:
            message += "of '{}' ".format(key)
        message += "is not one of the following: {}.".format(", ".join(human_types))
        raise LoadError(message, LoadErrorReason.INVALID_DATA)
