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

from ._exceptions import LoadError
from .exceptions import LoadErrorReason
from .node cimport MappingNode, Node, ScalarNode, SequenceNode, ProvenanceInformation

# Variables are allowed to have dashes here
#
PARSE_EXPANSION = re.compile(r"\%\{([a-zA-Z][a-zA-Z0-9_-]*)\}")

cdef Py_ssize_t MAX_RECURSION_DEPTH = 200

# Throughout this code you will see variables named things like `expstr`.
# These hold data structures called "expansion strings" and are the parsed
# form of the strings which are the input to this subsystem.  Strings
# such as "Hello %{name}, how are you?" are parsed into the form:
# ["Hello ", "name", ", how are you?"]
# i.e. a list which consists of one or more strings.
# Strings in even indices of the list (0, 2, 4, etc) are constants which
# are copied into the output of the expansion algorithm.  Strings in the
# odd indices (1, 3, 5, etc) are the names of further expansions to make.
# In the example above, first "Hello " is copied, then "name" is expanded
# and so must be another named expansion string passed in to the constructor
# of the Variables class, and whatever is yielded from the expansion of "name"
# is added to the concatenation for the result.  Finally ", how are you?" is
# copied in and the whole lot concatenated for return.
#
# To see how strings are parsed, see `_parse_value_expression()` after the class, and
# to see how expansion strings are expanded, see `_expand_value_expression()` after that.


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

    cdef MappingNode _original
    cdef dict _values

    #################################################################
    #                        Magic Methods                          #
    #################################################################
    def __init__(self, MappingNode node):

        # The original MappingNode, we need to keep this
        # around for proper error reporting.
        #
        self._original = node

        # The value map, this dictionary contains either unresolved
        # value expressions, or resolved values.
        #
        # Each mapping value is a list, in the case that the value
        # is resolved, then the list is only 1 element long.
        #
        self._values = self._init_values(node)

    # __getitem__()
    #
    # Fetches a resolved variable by it's name, allows
    # addressing the Variables instance like a dictionary.
    #
    # Args:
    #    name (str): The name of the variable
    #
    # Returns:
    #    (str): The resolved variable value
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    def __getitem__(self, str name):
        if name not in self._values:
            raise KeyError(name)

        return self._expand_var(name)

    # __contains__()
    #
    # Checks whether a given variable exists, allows
    # supporting `if 'foo' in variables` expressions.
    #
    # Args:
    #    name (str): The name of the variable to check for
    #
    # Returns:
    #    (bool): True if `name` is a valid variable
    #
    def __contains__(self, str name):
        return name in self._values

    # __iter__()
    #
    # Provide an iterator for all variables effective values
    #
    # Returns:
    #   (Iterator[Tuple[str, str]])
    #
    def __iter__(self):
        return _VariablesIterator(self)

    #################################################################
    #                          Public API                           #
    #################################################################

    # check()
    #
    # Assert that all variables declared on this Variables
    # instance have been resolved properly, and reports errors
    # for undefined references and circular references.
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    cpdef check(self):
        cdef object key

        # Just resolve all variables.
        for key in self._values.keys():
            self._expand_var(<str> key)

    # get()
    #
    # Expand definition of variable by name. If the variable is not
    # defined, it will return None instead of failing.
    #
    # Args:
    #    name (str): Name of the variable to expand
    #
    # Returns:
    #    (str|None): The expanded value for the variable or None variable was not defined.
    #
    cpdef str get(self, str name):
        if name not in self._values:
            return None
        return self[name]

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
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    cpdef expand(self, Node node):
        if isinstance(node, ScalarNode):
            (<ScalarNode> node).value = self.subst(<ScalarNode> node)
        elif isinstance(node, SequenceNode):
            for entry in (<SequenceNode> node).value:
                self.expand(entry)
        elif isinstance(node, MappingNode):
            for entry in (<MappingNode> node).value.values():
                self.expand(entry)
        else:
            assert False, "Unknown 'Node' type"

    # subst():
    #
    # Substitutes any variables in 'string' and returns the result.
    #
    # Args:
    #    node (ScalarNode): The ScalarNode to substitute variables in
    #
    # Returns:
    #    (str): The new string with any substitutions made
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    cpdef str subst(self, ScalarNode node):
        value_expression = _parse_value_expression(node.as_str())
        return self._expand_value_expression(value_expression, node)

    #################################################################
    #                          Private API                          #
    #################################################################

    # Variable resolving code
    #
    # Here we resolve all of our inputs into a dictionary, ready for use
    # in subst()
    cdef dict _init_values(self, MappingNode node):
        # Special case, if notparallel is specified in the variables for this
        # element, then override max-jobs to be 1.
        # Initialize it as a string as all variables are processed as strings.
        #
        if node.get_bool('notparallel', False):
            node['max-jobs'] = str(1)

        cdef dict ret = {}
        cdef str key
        cdef str value

        for key in node.keys():
            value = node.get_str(key)
            ret[sys.intern(key)] = _parse_value_expression(value)
        return ret

    #################################################################
    #                     Resolution algorithm                      #
    #################################################################
    #
    # This is split into a fast path and a slower path, with a small
    # calling layer in between for expanding variables and for expanding
    # value expressions which refer to variables expected to be defined
    # in this Variables instance.
    #
    # The fast path is initially used, it supports limited variable
    # expansion depth due to it's recursive nature, and does not support
    # full error reporting.
    #
    # The fallback slower path is non-recursive and reports user facing
    # errors, it is called in the case that KeyError or RecursionError
    # are reported from the faster path.
    #

    # _expand_var()
    #
    # Helper to expand and cache a variable definition.
    #
    # Args:
    #     name (str): Name of the variable to expand
    #
    # Returns:
    #     (str): The expanded value of variable
    #
    # Raises:
    #     KeyError, if any expansion is missing
    #     RecursionError, if recursion required for evaluation is too deep
    #
    cdef str _expand_var(self, str name):
        try:
            return self._fast_expand_var(name)
        except (KeyError, RecursionError):
            return self._slow_expand_var(name)

    # _expand_value_expression()
    #
    # Expands a given top level expansion string.
    #
    # Args:
    #    value_expression (list): The parsed value expression to be expanded
    #    node (ScalarNode): The toplevel ScalarNode who is asking for an expansion
    #
    # Returns:
    #    (str): The expanded value expression
    #
    # Raises:
    #    KeyError, if any expansion is missing
    #    RecursionError, if recursion required for evaluation is too deep
    #
    cdef str _expand_value_expression(self, list value_expression, ScalarNode node):
        try:
            return self._fast_expand_value_expression(value_expression)
        except (KeyError, RecursionError):
            return self._slow_expand_value_expression(None, value_expression, node)

    #################################################################
    #             Resolution algorithm: fast path                   #
    #################################################################
    cdef str _fast_expand_var(self, str name, int counter = 0):
        cdef str sub
        cdef list value_expression

        value_expression = <list> self._values[name]
        if len(value_expression) > 1:
            sub = self._fast_expand_value_expression(value_expression, counter)
            value_expression = [sys.intern(sub)]
            self._values[name] = value_expression

        return <str> value_expression[0]

    cdef str _fast_expand_value_expression(self, list value, int counter = 0):
        if counter > MAX_RECURSION_DEPTH:
            raise RecursionError()

        cdef Py_ssize_t idx
        cdef object val
        cdef list acc = []

        for idx, val in enumerate(value):
            if (idx % 2) == 0:
                acc.append(val)
            else:
                acc.append(self._fast_expand_var(<str> val, counter + 1))

        return "".join(acc)

    #################################################################
    #             Resolution algorithm: slow path                   #
    #################################################################

    # _get_checked_value_expression()
    #
    # Fetches a value expression from the value table and raises a user
    # facing error if the value is undefined.
    #
    # Args:
    #    varname (str): The variable name to fetch
    #    referee (str): The variable name referring to `varname`, or None
    #    node (ScalarNode): The ScalarNode for which we need to resolve `name`
    #
    # Returns:
    #    (list): The value expression for varname
    #
    # Raises:
    #    (LoadError): An appropriate error in case of undefined variables
    #
    cdef list _get_checked_value_expression(self, str varname, str referee, ScalarNode node):
        cdef ProvenanceInformation provenance = None
        cdef Node referee_value
        cdef str error_message

        #
        # Fetch the value and detect undefined references
        #
        try:
            return <list> self._values[varname]
        except KeyError as e:

            # Either the provenance is the toplevel calling provenance,
            # or it is the provenance of the direct referee
            referee_node = self._original.get_node(referee, allowed_types=None, allow_none=True)
            if referee_node:
                provenance = referee_node.get_provenance()
            elif node:
                provenance = node.get_provenance()

            error_message = "Reference to undefined variable '{}'".format(varname)
            if provenance:
                error_message = "{}: {}".format(provenance, error_message)
            raise LoadError(error_message, LoadErrorReason.UNRESOLVED_VARIABLE) from e

    cdef str _slow_expand_var(self, str name):
        cdef list value_expression
        cdef str expanded

        value_expression = self._get_checked_value_expression(name, None, None)
        if len(value_expression) > 1:
            expanded = self._slow_expand_value_expression(name, value_expression, None)
            value_expression = [sys.intern(expanded)]
            self._values[name] = value_expression

        return <str> value_expression[0]

    cdef str _slow_expand_value_expression(self, str varname, list value_expression, ScalarNode node):
        cdef ResolutionStep step
        cdef ResolutionStep new_step
        cdef ResolutionStep this_step
        cdef list iter_value_expression
        cdef Py_ssize_t idx = 0
        cdef object value
        cdef str resolved_varname
        cdef str resolved_value = None

        # We will collect the varnames and value expressions which need
        # to be resolved in the loop, sorted by dependency, and then
        # finally reverse through them resolving them one at a time
        #
        cdef list resolved_varnames = []
        cdef list resolved_values = []
        
        step = ResolutionStep()
        step.init(varname, value_expression, None)
        while step:
            # Keep a hold of the current overall step
            this_step = step
            step = step.prev

            # Check for circular dependencies
            this_step.check_circular(self._original)

            for idx, value in enumerate(this_step.value_expression):

                # Skip literal parts of the value expression
                if (idx % 2) == 0:
                    continue

                iter_value_expression = self._get_checked_value_expression(<str> value, this_step.referee, node)

                # Queue up this value.
                #
                # Even if the value was already resolved, we need it in context to resolve
                # previously enqueued variables
                resolved_values.append(iter_value_expression)
                resolved_varnames.append(value)

                # Queue up the values dependencies.
                #
                if len(iter_value_expression) > 1:
                    new_step = ResolutionStep()
                    new_step.init(<str> value, iter_value_expression, this_step)

                    # Link it to the end of the stack
                    new_step.prev = step
                    step = new_step

        # We've now constructed the dependencies queue such that
        # later dependencies are on the right, we can now safely peddle
        # backwards and the last (leftmost) resolved value is the one
        # we want to return.
        #
        idx = len(resolved_values) -1
        while idx >= 0:
            # Values in, strings out
            #
            iter_value_expression = <list> resolved_values[idx]
            resolved_varname = <str> resolved_varnames[idx]

            # Resolve as needed
            #
            if len(iter_value_expression) > 1:
                resolved_value = self._resolve_value_expression(iter_value_expression)
                iter_value_expression = [resolved_value]
                if resolved_varname is not None:
                    self._values[resolved_varname] = iter_value_expression

            idx -= 1

        return resolved_value

    cdef str _resolve_value_expression(self, list value_expression):
        cdef Py_ssize_t idx
        cdef object value
        cdef list acc = []

        for idx, value in enumerate(value_expression):
            if (idx % 2) == 0:
                acc.append(value)
            else:
                acc.append(self._values[value][0])

        return "".join(acc)


# ResolutionStep()
#
# The context for a single iteration in variable resolution.
#
# This only exists for better performance than constructing
# and unpacking tuples.
#
cdef class ResolutionStep:
    cdef str referee
    cdef list value_expression
    cdef ResolutionStep parent
    cdef ResolutionStep prev

    # init()
    #
    # Initialize this ResolutionStep
    #
    # Args:
    #    referee (str): The name of the referring variable
    #    value_expression (list): The parsed value expression to be expanded
    #    parent (ResolutionStep): The parent ResolutionStep
    #
    cdef init(self, str referee, list value_expression, ResolutionStep parent):
        self.referee = referee
        self.value_expression = value_expression
        self.parent = parent
        self.prev = None

    # check_circular()
    #
    # Check for circular references in this step.
    #
    # Args:
    #    original_values (MappingNode): The original MappingNode for the Variables
    #
    # Raises:
    #    (LoadError): Will raise a user facing LoadError with
    #                 LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE in case
    #                 circular references were encountered.
    #
    cdef check_circular(self, MappingNode original_values):
        cdef ResolutionStep step = self.parent
        while step:
            if self.referee is step.referee:
                self._raise_circular_reference_error(step, original_values)
            step = step.parent

    # _raise_circular_reference_error()
    #
    # Helper function to construct a full report and raise the circular reference error.
    #
    cdef _raise_circular_reference_error(self, ResolutionStep conflict, MappingNode original_values):
        cdef list error_lines = []
        cdef ResolutionStep step = self
        cdef ScalarNode node
        cdef str referee

        while step is not conflict:
            if step.parent:
                referee = step.parent.referee
            else:
                referee = self.referee

            node = original_values.get_scalar(referee)

            error_lines.append("{}: Variable '{}' refers to variable '{}'".format(node.get_provenance(), referee, step.referee))
            step = step.parent

        raise LoadError("Circular dependency detected on variable '{}'".format(self.referee),
                        LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE,
                        detail="\n".join(reversed(error_lines)))


# Cache for the parsed expansion strings.  While this is nominally
# something which might "waste" memory, in reality each of these
# will live as long as the element which uses it, which is the
# vast majority of the memory usage across the execution of BuildStream.
cdef dict VALUE_EXPRESSION_CACHE = {
    # Prime the cache with the empty string since otherwise that can
    # cause issues with the parser, complications to which cause slowdown
    "": [""],
}


# Helper to parse a string into an expansion string tuple, caching
# the results so that future parse requests don't need to think about
# the string
cdef list _parse_value_expression(str instr):
    cdef list ret

    try:
        return <list> VALUE_EXPRESSION_CACHE[instr]
    except KeyError:
        # This use of the regex turns a string like "foo %{bar} baz" into
        # a list ["foo ", "bar", " baz"]
        splits = PARSE_EXPANSION.split(instr)
        # If an expansion ends the string, we get an empty string on the end
        # which we can optimise away, making the expansion routines not need
        # a test for this.
        if splits[-1] == '':
           del splits [-1]
        # Cache an interned copy of this.  We intern it to try and reduce the
        # memory impact of the cache.  It seems odd to cache the list length
        # but this is measurably cheaper than calculating it each time during
        # string expansion.
        ret = [sys.intern(<str> s) for s in <list> splits]
        VALUE_EXPRESSION_CACHE[instr] = ret
        return ret


# Iterator for all flatten variables.
# Used by Variables.__iter__
cdef class _VariablesIterator:
    cdef Variables _variables
    cdef object _iter

    def __init__(self, Variables variables):
        self._variables = variables
        self._iter = iter(variables._values)

    def __iter__(self):
        return self

    def __next__(self):
        name = next(self._iter)
        return name, self._variables._expand_var(name)
