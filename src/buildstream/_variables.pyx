#
#  Copyright (C) 2020 Codethink Limited
#  Copyright (C) 2019 Bloomberg L.P.
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
#        Benjamin Schubert <bschubert@bloomberg.net>

import re
import sys
import itertools

from cpython.mem cimport PyMem_Malloc, PyMem_Free, PyMem_Realloc
from cpython.object cimport PyObject
from cpython.ref cimport Py_XINCREF, Py_XDECREF

from ._profile import Topics, PROFILER
from ._exceptions import LoadError
from .exceptions import LoadErrorReason
from .node cimport MappingNode, Node, ScalarNode, SequenceNode, ProvenanceInformation


ctypedef struct ObjectArray:
    Py_ssize_t length
    PyObject **array

    # Private, actual size of the allocated vector
    Py_ssize_t _size


# The Variables helper object will resolve the variable references in
# the given dictionary, expecting that any dictionary values which contain
# variable references can be resolved from the same dictionary.
#
# Each Element creates its own Variables instance to track the configured
# variable settings for the element.
#
# Args:
#     node (Node): A node loaded and composited with yaml tools
#
# Raises:
#     LoadError, if unresolved variables, or cycles in resolution, occur.
#
cdef class Variables:

    cdef dict _values  # The Value objects
    cdef MappingNode _origin

    def __init__(self, MappingNode node):

        self._origin = node

        # Special case, if notparallel is specified in the variables for this
        # element, then override max-jobs to be 1.
        # Initialize it as a string as all variables are processed as strings.
        #
        if node.get_bool('notparallel', False):
            #
            # The MappingNode API will automatically convert this `str(1)`
            # into a ScalarNode, no need to manually create the ScalarNode here.
            #
            node['max-jobs'] = str(1)

        self._values = self._init_values(node)

    # __getitem__()
    #
    # Enables indexing access to variables.
    #
    # Args:
    #    name (str): The key
    #
    # Returns:
    #    (str): The value
    #
    def __getitem__(self, str name) -> str:
        return self._resolve(name, None)

    # __contains__()
    #
    # Implements syntaxes like `if "foo" in variables`
    #
    # Args:
    #    name (str): The key
    #
    # Returns:
    #    (bool): Whether the name exists as a key in this variables mapping
    #
    def __contains__(self, str name) -> bool:
        return name in self._values

    # __iter__()
    #
    # Implements the iterator interface so that we can iterate over the
    # Variables type, this also allows transformation of the Variables
    # type into a simple dictionary where the keys are the variable names
    # and the values are the fully resolve values.
    #
    # Returns:
    #    (Iterator[Tuple[str, str]]): The variable names and resolved values
    #
    def __iter__(self):
        return ValueIterator(self, self._values)

    # get()
    #
    # Expand definition of variable by name. If the variable is not
    # defined, it will return None instead of failing.
    #
    # Args:
    #   name (str): Name of the variable to expand
    #
    # Returns:
    #   (str|None): The expanded value for the variable or None variable was not defined.
    #
    cpdef str get(self, str name):
        try:
            return <str> self._resolve(name, None)
        except LoadError as e:
            if e.reason == LoadErrorReason.UNRESOLVED_VARIABLE:
                return None

    # expand()
    #
    # Expand all the variables found in the given Node, recursively.
    # This does the change in place, modifying the node. If you want to keep
    # the node untouched, you should use `node.clone()` beforehand
    #
    # Args:
    #    (Node): A node for which to substitute the values
    #
    # Raises:
    #    (LoadError): if the string contains unresolved variable references.
    #
    cpdef expand(self, Node node):
        self._expand(node)

    # subst():
    #
    # Substitutes any variables in 'string' and returns the result.
    #
    # Args:
    #    (string): The string to substitute
    #
    # Returns:
    #    (string): The new string with any substitutions made
    #
    # Raises:
    #    (LoadError): if the string contains unresolved variable references.
    #
    cpdef str subst(self, ScalarNode node):
        return self._subst(node)

    # check()
    #
    # Checks the variables for unresolved references
    #
    # Raises:
    #    (LoadError): If there are unresolved references, then a LoadError
    #                 with LoadErrorReason.UNRESOLVED_VARIABLE reason will
    #                 be raised.
    #
    cpdef check(self):
        cdef object key

        with PROFILER.profile(Topics.VARIABLES_CHECK, id(self._origin)):
            # Resolve all variables.
            for key in self._values.keys():
                self._resolve(<str> key, None)

    # _init_values()
    #
    # Here we initialize the Value() table, which contains
    # as of yet unresolved variables.
    #
    cdef dict _init_values(self, MappingNode node):
        cdef dict ret = {}
        cdef object key
        cdef object value_node
        cdef Value value

        with PROFILER.profile(Topics.VARIABLES_INIT, id(self._origin)):

            for key, value_node in node.items():
                value = Value()
                value.init(<ScalarNode> value_node)
                ret[key] = value

        return ret

    # _subst():
    #
    # Internal implementation of Variables.subst()
    #
    # Args:
    #    (string): The string to substitute
    #
    # Returns:
    #    (string): The new string with any substitutions made
    #
    # Raises:
    #    (LoadError): if the string contains unresolved variable references.
    #
    cpdef str _subst(self, ScalarNode node):
        cdef Value value = Value()
        cdef ObjectArray *dependencies
        cdef Py_ssize_t idx = 0
        cdef str dep_name

        value.init(node)
        dependencies = value.dependencies()
        while idx < dependencies.length:
            dep_name = <str> dependencies.array[idx]
            self._resolve(dep_name, node)
            idx += 1

        return value.resolve(self._values)

    # _expand()
    #
    # Internal implementation of Variables.expand()
    #
    # Args:
    #   (Node): A node for which to substitute the values
    #
    # Raises:
    #   (LoadError): if the string contains unresolved variable references.
    #
    cdef _expand(self, Node node):
        cdef object entry
        if isinstance(node, ScalarNode):
            (<ScalarNode> node).value = self._subst(<ScalarNode> node)
        elif isinstance(node, SequenceNode):
            for entry in (<SequenceNode> node).value:
                self._expand(<Node> entry)
        elif isinstance(node, MappingNode):
            for entry in (<MappingNode> node).value.values():
                self._expand(<Node> entry)
        else:
            assert False, "Unknown 'Node' type"

    # _resolve()
    #
    # Helper to expand and cache a variable definition in the context of
    # the given dictionary of expansion strings.
    #
    # Args:
    #    name (str): Name of the variable to expand
    #    pnode (ScalarNode): The ScalarNode for which we need to resolve `name`
    #
    # Returns:
    #    (str): The expanded value of variable
    #
    # Raises:
    #    (LoadError): In case there was any undefined variables or circular
    #                 references encountered when resolving the variable.
    #
    cdef str _resolve(self, str name, ScalarNode pnode):
        cdef ResolutionStep step
        cdef ResolutionStep new_step
        cdef ResolutionStep this_step

        cdef Value iter_value
        cdef str iter_name

        cdef ObjectArray *iter_value_deps
        cdef Py_ssize_t idx = 0

        cdef str resolved_value = None
        cdef bint first_iteration = True

        # We'll be collecting the values to resolve at the end in here
        cdef ObjectArray values
        object_array_init(&(values), -1)

        # While iterating over the first loop, we collect all of the variable
        # dependencies, and perform all required validation.
        #
        # Each iteration processes a ResolutionStep object and has the possibility
        # to enque more ResolutionStep objects as a result.
        #
        cdef ObjectArray initial_deps
        object_array_init(&(initial_deps), 1)
        object_array_append(&(initial_deps), <PyObject *>name)

        step = ResolutionStep()
        step.init(None, &(initial_deps), None)

        while step:
            # Keep a hold of the current overall step
            this_step = step
            step = step.prev

            # Check for circular dependencies
            this_step.check_circular(self._values)

            idx = 0
            while idx < this_step.varnames.length:
                iter_name = <str> this_step.varnames.array[idx]
                iter_value = self._get_checked_value(iter_name, this_step.referee, pnode)
                idx += 1

                # Earliest return for an already resolved value
                #
                if first_iteration:
                    if iter_value._resolved is not None:
                        return iter_value.resolve(self._values)
                    first_iteration = False

                # Queue up this value to be resolved in the next loop
                if iter_value._resolved is None:

                    object_array_append(&(values), <PyObject *>iter_value)

                    # Queue up it's dependencies for resolution
                    iter_value_deps = iter_value.dependencies()
                    if iter_value_deps:
                        new_step = ResolutionStep()
                        new_step.init(iter_name, iter_value_deps, this_step)

                        # Link it to the end of the stack
                        new_step.prev = step
                        step = new_step

        # We've now constructed the dependencies queue such that
        # later dependencies are on the right, we can now safely peddle
        # backwards and the last (leftmost) resolved value is the one
        # we want to return.
        #
        idx = values.length -1
        while idx >= 0:
            iter_value = <Value>values.array[idx]
            resolved_value = iter_value.resolve(self._values)
            idx -= 1

        # Cleanup
        #
        object_array_free(&(initial_deps))
        object_array_free(&(values))

        return resolved_value

    # _get_checked_value()
    #
    # Fetches a value from the value table and raises a user
    # facing error if the value is undefined.
    #
    # Args:
    #    varname (str): The variable name to fetch
    #    referee (str): The variable name referring to `varname`, or None
    #    pnode (ScalarNode): The ScalarNode for which we need to resolve `name`
    #
    # Returns:
    #   (Value): The Value for varname
    #
    # Raises:
    #   (LoadError): An appropriate error in case of undefined variables
    #
    cdef Value _get_checked_value(self, str varname, str referee, ScalarNode pnode):
        cdef ProvenanceInformation provenance = None
        cdef Value referee_value
        cdef str error_message

        #
        # Fetch the value and detect undefined references
        #
        try:
            return <Value> self._values[varname]
        except KeyError as e:

            # Either the provenance is the toplevel calling provenance,
            # or it is the provenance of the direct referee
            try:
                referee_value = self._values[referee]
            except KeyError:
                referee_value = None

            if referee_value:
                provenance = referee_value.get_provenance()
            elif pnode:
                provenance = pnode.get_provenance()
            error_message = "Reference to undefined variable '{}'".format(varname)

            if provenance:
                error_message = "{}: {}".format(provenance, error_message)
            raise LoadError(error_message, LoadErrorReason.UNRESOLVED_VARIABLE) from e


# ResolutionStep()
#
# The context for a single iteration in variable resolution.
#
# This only exists for better performance than constructing
# and unpacking tuples.
#
cdef class ResolutionStep:
    cdef str referee
    cdef ResolutionStep parent
    cdef ResolutionStep prev
    cdef ObjectArray *varnames

    # init()
    #
    # Initialize this ResolutionStep
    #
    # Args:
    #    referee (str): The name of the referring variable
    #    varnames (set): A set of variable names which referee refers to.
    #    parent (ResolutionStep): The parent ResolutionStep
    #
    cdef init(self, str referee, ObjectArray *varnames, ResolutionStep parent):
        self.referee = referee
        self.varnames = varnames
        self.parent = parent
        self.prev = None

    # check_circular()
    #
    # Check for circular references in this step.
    #
    # Args:
    #    values (dict): The value dictionary for lookups
    #
    # Raises:
    #    (LoadError): Will raise a user facing LoadError with
    #                 LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE in case
    #                 circular references were encountered.
    #
    cdef check_circular(self, dict values):
        cdef ResolutionStep step = self.parent
        while step:
            if self.referee is step.referee:
                self._raise_circular_reference_error(step, values)
            step = step.parent

    # _raise_circular_reference_error()
    #
    # Helper function to construct a full report and raise the circular reference error.
    #
    cdef _raise_circular_reference_error(self, ResolutionStep conflict, dict values):
        cdef list error_lines = []
        cdef ResolutionStep step = self
        cdef Value value
        cdef str referee

        while step is not conflict:
            if step.parent:
                referee = step.parent.referee
            else:
                referee = self.referee
            value = values[referee]

            error_lines.append("{}: Variable '{}' refers to variable '{}'".format(value.get_provenance(), referee, step.referee))
            step = step.parent

        raise LoadError("Circular dependency detected on variable '{}'".format(self.referee),
                        LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE,
                        detail="\n".join(reversed(error_lines)))


cdef EMPTY_SET = set()

# Value():
#
# Represents a variable value
#
cdef class Value:
    cdef ScalarNode _node
    cdef ValueClass _value_class
    cdef str _resolved

    # init()
    #
    # Initialize the Value
    #
    # Args:
    #    node (ScalarNode): The node representing this value.
    #
    cdef init(self, ScalarNode node):
        self._node = node
        self._value_class = self._load_value_class(node.as_str())
        self._resolved = None

    # get_provenance():
    #
    # Fetches the provenance of this Value
    #
    # Returns:
    #    (ProvenanceInformation): The provenance of this Value
    #
    cdef get_provenance(self):
        return self._node.get_provenance()

    # resolve()
    #
    # Resolve the value of this variable, this function expects
    # all dependency values to already be resolved, otherwise
    # it will fail due to an undefined variable.
    #
    # Args:
    #    values (dict): The full value table for resolving dependencies
    #
    # Returns:
    #    (str): The resolved value
    #
    cdef str resolve(self, dict values):
        cdef str dep_name
        cdef Value part_var
        cdef ValuePart *part
        cdef object part_object
        cdef list parts = []

        if self._resolved is None:
            part = self._value_class.parts

            while part:
                if part.is_variable:
                    part_var = <Value> values[<str>part.text]
                    parts.append(part_var._resolved)
                else:
                    parts.append(<str>part.text)

                part = part.next_part

            self._resolved = "".join(parts)

        return self._resolved

    # dependencies()
    #
    # Returns the array of dependency variable names
    #
    # Returns:
    #    (ObjectArray *): The array of variable names, or NULL
    #
    cdef ObjectArray *dependencies(self):
        if self._resolved is None:
            return &(self._value_class.varnames)

        # If we're already resolved, we don't have any dependencies anymore
        return NULL

    # _load_value_class()
    #
    # Load the ValueClass for this Value, possibly reusing
    # a pre-cached ValueClass if one exists.
    #
    # Args:
    #    string (str): The string to parse
    #
    # Returns:
    #    (ValueClass): The ValueClass object
    #
    cdef ValueClass _load_value_class(self, str string):
        cdef ValueClass ret

        string = sys.intern(string)

        try:
            ret = VALUE_CLASS_TABLE[string]
        except KeyError:
            ret = ValueClass()
            ret.init(string)
            VALUE_CLASS_TABLE[string] = ret

        return ret


# Global cache of all ValueClass objects ever instantiated.
#
# While many elements share exactly the same ValueClasses, they
# all have their own Value instances and can resolve to different
# string values.
#
# Holding on to this avoids ever parsing the same value strings
# more than once.
#
cdef dict VALUE_CLASS_TABLE = {}


#
# The regular expression used for parsing ValueClass strings.
#
# Note that Variable names are allowed to have alphanumeric characters
# and dashes and underscores, but cannot start with a dash, underscore
# or a digit.
#
VALUE_CLASS_PARSE_EXPANSION = re.compile(r"\%\{([a-zA-Z][a-zA-Z0-9_-]*)\}")


# ValueClass()
#
# A class representing a broken down parse of a value.
#
cdef class ValueClass:
    #
    # Public
    #
    cdef ValuePart *parts
    cdef ObjectArray varnames

    # __dealloc__()
    #
    # Cleanup stuff which cython wont cleanup automatically
    #
    def __dealloc__(self):
        free_value_parts(self.parts)
        object_array_free(&(self.varnames))

    # init():
    #
    # Initialize the ValueClass()
    #
    # Args:
    #    string (str): The string which can contain variables
    #
    cdef init(self, str string):
        self.parts = NULL
        self._parse_string(string)

    # _parse_string()
    #
    # Parse the string for this ValueClass, breaking it down into
    # the parts list, which is an ordered list of literal values
    # and variable names, which when resolved, can be joined into
    # the resolved value.
    #
    cdef _parse_string(self, str string):

        # This use of this regex turns a string like
        # "foo %{bar} baz" into a list ["foo ", "bar", " baz"]
        #
        # This split has special properties in that it will
        # return empty strings, and even/odd members of the
        # returned list are meaningful.
        #
        # The even number indices are slices of the text which
        # did not match the regular expression, while the odd
        # number indices represent variable names, with the "%{}"
        # portions stripped away.
        #
        # In case you are still wondering: Yes. This is very, very weird.
        #
        # What do you expect ? These are regular expressions after all,
        # they are *supposed* to be weird.
        #
        cdef list splits = VALUE_CLASS_PARSE_EXPANSION.split(string)
        cdef object split_object
        cdef str split
        cdef Py_ssize_t idx = 0
        cdef Py_ssize_t n_variables = 0
        cdef int is_variable

        # Adding parts
        #
        cdef ValuePart *part
        cdef ValuePart *last_part = NULL

        #
        # Collect the weird regex return value into something
        # more comprehensible.
        #
        for split_object in splits:
            split = <str> split_object
            if split:

                if (idx % 2) == 0:
                    is_variable = False
                else:
                    n_variables += 1
                    is_variable = True

                part = new_value_part(split, is_variable)
                if last_part:
                    last_part.next_part = part
                else:
                    self.parts = part
                last_part = part

            idx += 1

        # Initialize the variables array
        #
        object_array_init(&(self.varnames), n_variables)
        part = self.parts
        while part:
            if part.is_variable:
                object_array_append(&(self.varnames), part.text)
            part = part.next_part

# ValueIterator()
#
# Iterator for all flatten variables.
#
# Used by Variables.__iter__
#
cdef class ValueIterator:
    cdef Variables _variables
    cdef object _iter

    def __cinit__(self, Variables variables, dict values):
        self._variables = variables
        self._iter = iter(values)

    def __iter__(self):
        return self

    def __next__(self):
        name = next(self._iter)
        return name, self._variables[name]


############################## BASEMENT ########################################

cdef int OBJECT_ARRAY_BLOCK_SIZE = 8


# object_array_init()
#
# Initialize the object array
#
# Args:
#    array (ObjectArray *): The array to initialize
#    size (Py_ssize_t): The initial size of the array, or < 0 for an automatic size,
#                       0 for no allocated buffer initially
#
# Raises:
#    (MemoryError): In the case we failed to allocate memory for the array
#
cdef void object_array_init(ObjectArray *array, Py_ssize_t size):
    array._size = size
    if array._size < 0:
        array._size = OBJECT_ARRAY_BLOCK_SIZE
    array.length = 0
    if array._size > 0:
        array.array = <PyObject **>PyMem_Malloc(array._size * sizeof(PyObject *))
        if not array.array:
            raise MemoryError()
    else:
        array.array = NULL


# object_array_append()
#
# Append an object to the array
#
# Args:
#    array (ObjectArray *): The array to append to
#    obj (PyObject *): The object to append to the array
#
# Raises:
#    (MemoryError): In the case we failed to allocate memory for the array
#
cdef void object_array_append(ObjectArray *array, PyObject *obj):

    # Ensure we have enough space for the new item
    if array.length >= array._size:
        array._size = array._size + OBJECT_ARRAY_BLOCK_SIZE - (array._size % 8)
        array.array = <PyObject **>PyMem_Realloc(array.array, array._size * sizeof(PyObject *))
        if not array.array:
            raise MemoryError()

    Py_XINCREF(obj)
    array.array[array.length] = obj
    array.length += 1


# object_array_free()
#
# Free the array, releasing references to all the objects
#
# Args:
#    array (ObjectArray *): The array to free up
#
cdef void object_array_free(ObjectArray *array):
    cdef Py_ssize_t idx = 0
    while idx < array.length:
        Py_XDECREF(array.array[idx])
        idx += 1

    if array._size > 0:
        PyMem_Free(array.array)


# ValuePart()
#
# Represents a part of a value (a string and an indicator
# of whether the string is a variable or not).
#
# This only exists for better performance than constructing
# and unpacking tuples.
#
# Args:
#    text (str): The text of this part
#    is_variable (bint): True if the text is a variable, False if it's literal
#
ctypedef struct ValuePart:
    PyObject *text
    int is_variable
    ValuePart *next_part

cdef ValuePart *new_value_part(str text, int is_variable):
    cdef ValuePart *part = <ValuePart *>PyMem_Malloc(sizeof(ValuePart))
    if not part:
        raise MemoryError()

    part.text = <PyObject *>text
    part.is_variable = is_variable
    part.next_part = NULL
    Py_XINCREF(part.text)
    return part

cdef void free_value_part(ValuePart *part):
    Py_XDECREF(part.text)
    PyMem_Free(part)

cdef void free_value_parts(ValuePart *part):
    cdef ValuePart *to_free
    while part:
        to_free = part
        part = part.next_part
        free_value_part(to_free)
