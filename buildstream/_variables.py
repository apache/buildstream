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

from ._exceptions import LoadError, LoadErrorReason
from . import _yaml

########################################################
#           Understanding Value Expressions            #
########################################################
#
# This code uses the term "value expression" a lot to refer to `str` objects
# which have references to variables in them, and also to `list` objects which
# are effectively broken down strings.
#
# Ideally we would have a ValueExpression type in order to make this more
# comprehensive, but this would unfortunately introduce unnecessary overhead,
# making the code measurably slower.
#
# Value Expression Strings
# ------------------------
# Strings which contain variables in them, such as:
#
#      "My name is %{username}, good day."
#
#
# Parsed Value Expression Lists
# -----------------------------
# Using `re.split()` from python's regular expression implementation, we
# parse the list using our locally defined VALUE_EXPRESSION_REGEX, which
# breaks down the string into a list of "literal" and "variable" components.
#
# The "literal" components are literal portions of the string which need
# no substitution, while the "variable" components represent variable names
# which need to be substituted with their corresponding resolved values.
#
# The parsed variable expressions have the following properties:
#
#   * They are sparse, some of the "literal" values contain zero length
#     strings which can be ignored.
#
#   * Literal values are found only at even indices of the parsed
#     variable expression
#
#   * Variable names are found only at odd indices
#
# The above example "My name is %{username}, good day." is broken down
# into a parsed value expression as follows:
#
# [
#    "My name is ",   # <- Index 0, literal value
#    "username",      # <- Index 1, variable name, '%{ ... }' discarded
#    ", good day."    # <- Index 2, literal value
# ]
#

# Maximum recursion depth using the fast (recursive) variable resolution
# algorithm.
#
MAX_RECURSION_DEPTH = 200

# Regular expression used to parse %{variables} in value expressions
#
# Note that variables are allowed to have dashes
#
VALUE_EXPRESSION_REGEX = re.compile(r"\%\{([a-zA-Z][a-zA-Z0-9_-]*)\}")

# Cache for the parsed expansion strings.
#
VALUE_EXPRESSION_CACHE = {
    # Prime the cache with the empty string since otherwise that can
    # cause issues with the parser, complications to which cause slowdown
    "": [""],
}


# Variables()
#
# The Variables object resolves the variable references in the given MappingNode,
# expecting that any dictionary values which contain variable references can be
# resolved from the same dictionary.
#
# Each Element creates its own Variables instance to track the configured
# variable settings for the element.
#
# Notably, this object is delegated the responsibility of expanding
# variables in yaml Node hierarchies and substituting variables in strings
# in the context of a given Element's variable configuration.
#
# Args:
#     node (dict): A node loaded and composited with yaml tools
#
# Raises:
#     LoadError, if unresolved variables, or cycles in resolution, occur.
#
class Variables:

    #################################################################
    #                       Dunder Methods                          #
    #################################################################
    def __init__(self, node):

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
    def __getitem__(self, name):
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
    def __contains__(self, name):
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
    def check(self):

        # Just resolve all variables.
        for key in self._values:
            self._expand_var(key)

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
    def get(self, name):
        if name not in self._values:
            return None
        return self[name]

    # subst():
    #
    # Substitutes any variables in 'string' and returns the result.
    #
    # Args:
    #    string (str): The string to substitute
    #    provenance (Provenance): The provenance of the string
    #
    # Returns:
    #    (str): The new string with any substitutions made
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    def subst(self, string, provenance):
        value_expression = _parse_value_expression(string)
        return self._expand_value_expression(value_expression, provenance)

    #################################################################
    #                          Private API                          #
    #################################################################

    # _init_values()
    #
    # Initialize the table of values.
    #
    # The value table is a dictionary keyed by the variable names where
    # the values are value expressions (lists) which are initially unresolved.
    #
    # Value expressions are later resolved on demand and replaced in this
    # table with single element lists.
    #
    # Args:
    #    node (dict): The original variables mapping node
    #
    # Returns:
    #    (dict): A dictionary of value expressions (lists)
    #
    def _init_values(self, node):
        # Special case, if notparallel is specified in the variables for this
        # element, then override max-jobs to be 1.
        # Initialize it as a string as all variables are processed as strings.
        #
        if _yaml.node_get(node, bool, 'notparallel', default_value=False):
            node['max-jobs'] = str(1)

        ret = {}
        for key in node.keys():
            value = _yaml.node_get(node, str, key)
            ret[sys.intern(key)] = _parse_value_expression(value)

        return ret

    # _expand_var()
    #
    # Expand and cache a variable definition.
    #
    # This will try the fast, recursive path first and fallback to
    # the slower iterative codepath.
    #
    # Args:
    #    name (str): Name of the variable to expand
    #
    # Returns:
    #    (str): The expanded value of variable
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    def _expand_var(self, name):
        try:
            return self._fast_expand_var(name)
        except (KeyError, RecursionError):
            return self._slow_expand_var(name)

    # _expand_value_expression()
    #
    # Expands a value expression
    #
    # This will try the fast, recursive path first and fallback to
    # the slower iterative codepath.
    #
    # Args:
    #    value_expression (list): The parsed value expression to be expanded
    #    provenance (Provenance): The provenance of the value expression
    #
    # Returns:
    #    (str): The expanded value expression
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    def _expand_value_expression(self, value_expression, provenance):
        try:
            return self._fast_expand_value_expression(value_expression)
        except (KeyError, RecursionError):
            return self._slow_expand_value_expression(None, value_expression, provenance)

    #################################################################
    #             Resolution algorithm: fast path                   #
    #################################################################

    # _fast_expand_var()
    #
    # Fast, recursive path for variable expansion
    #
    # Args:
    #    name (str): Name of the variable to expand
    #    counter (int): Number of recursion cycles (used only in recursion)
    #
    # Returns:
    #    (str): The expanded value of variable
    #
    # Raises:
    #    (KeyError): If a reference to an undefined variable is encountered
    #    (RecursionError): If MAX_RECURSION_DEPTH recursion cycles is reached
    #
    def _fast_expand_var(self, name, counter=0):

        value_expression = self._values[name]
        if len(value_expression) > 1:
            sub = self._fast_expand_value_expression(value_expression, counter)
            value_expression = [sys.intern(sub)]
            self._values[name] = value_expression

        return value_expression[0]

    # _fast_expand_value_expression()
    #
    # Fast, recursive path for value expression expansion.
    #
    # Args:
    #    value_expression (list): The parsed value expression to be expanded
    #    counter (int): Number of recursion cycles (used only in recursion)
    #
    # Returns:
    #    (str): The expanded value expression
    #
    # Raises:
    #    (KeyError): If a reference to an undefined variable is encountered
    #    (RecursionError): If MAX_RECURSION_DEPTH recursion cycles is reached
    #
    def _fast_expand_value_expression(self, value_expression, counter=0):
        if counter > MAX_RECURSION_DEPTH:
            raise RecursionError()

        acc = []
        for idx, value in enumerate(value_expression):
            if (idx % 2) == 0:
                acc.append(value)
            else:
                acc.append(self._fast_expand_var(value, counter + 1))

        return "".join(acc)

    #################################################################
    #             Resolution algorithm: slow path                   #
    #################################################################

    # _slow_expand_var()
    #
    # Slow, iterative path for variable expansion with full error reporting
    #
    # Args:
    #    name (str): Name of the variable to expand
    #
    # Returns:
    #    (str): The expanded value of variable
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    def _slow_expand_var(self, name):
        value_expression = self._get_checked_value_expression(name, None, None)
        if len(value_expression) > 1:
            expanded = self._slow_expand_value_expression(name, value_expression, None)
            value_expression = [sys.intern(expanded)]
            self._values[name] = value_expression

        return value_expression[0]

    # _slow_expand_value_expression()
    #
    # Slow, iterative path for value expression expansion with full error reporting
    #
    # Note that either `varname` or `node` must be provided, these are used to
    # identify the provenance of this value expression (which might be the value
    # of a variable, or a value expression found elswhere in project YAML which
    # needs to be substituted).
    #
    # Args:
    #    varname (str|None): The variable name associated with this value expression, if any
    #    value_expression (list): The parsed value expression to be expanded
    #    provenance (Provenance): The provenance who is asking for an expansion
    #
    # Returns:
    #    (str): The expanded value expression
    #
    # Raises:
    #    (LoadError): In the case of an undefined variable or
    #                 a cyclic variable reference
    #
    def _slow_expand_value_expression(self, varname, value_expression, provenance):
        idx = 0
        resolved_value = None

        # We will collect the varnames and value expressions which need
        # to be resolved in the loop, sorted by dependency, and then
        # finally reverse through them resolving them one at a time
        #
        resolved_varnames = []
        resolved_values = []

        step = ResolutionStep(varname, value_expression, None)
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

                iter_value_expression = self._get_checked_value_expression(value, this_step.referee, provenance)

                # Queue up this value.
                #
                # Even if the value was already resolved, we need it in context to resolve
                # previously enqueued variables
                resolved_values.append(iter_value_expression)
                resolved_varnames.append(value)

                # Queue up the values dependencies.
                #
                if len(iter_value_expression) > 1:
                    new_step = ResolutionStep(value, iter_value_expression, this_step)

                    # Link it to the end of the stack
                    new_step.prev = step
                    step = new_step

        # We've now constructed the dependencies queue such that
        # later dependencies are on the right, we can now safely peddle
        # backwards and the last (leftmost) resolved value is the one
        # we want to return.
        #
        for iter_value_expression, resolved_varname in zip(reversed(resolved_values), reversed(resolved_varnames)):

            # Resolve as needed
            #
            if len(iter_value_expression) > 1:
                resolved_value = self._resolve_value_expression(iter_value_expression)
                iter_value_expression = [resolved_value]
                if resolved_varname is not None:
                    self._values[resolved_varname] = iter_value_expression

        return resolved_value

    # _get_checked_value_expression()
    #
    # Fetches a value expression from the value table and raises a user
    # facing error if the value is undefined.
    #
    # Args:
    #    varname (str): The variable name to fetch
    #    referee (str): The variable name referring to `varname`, or None
    #    provenance (Provenance): The provenance for which we need to resolve `name`
    #
    # Returns:
    #    (list): The value expression for varname
    #
    # Raises:
    #    (LoadError): An appropriate error in case of undefined variables
    #
    def _get_checked_value_expression(self, varname, referee=None, provenance=None):

        #
        # Fetch the value and detect undefined references
        #
        try:
            return self._values[varname]
        except KeyError as e:

            # Either the provenance is the toplevel calling provenance,
            # or it is the provenance of the direct referee
            if referee:
                p = _yaml.node_get_provenance(self._original, referee)
            else:
                p = provenance

            error_message = "Reference to undefined variable '{}'".format(varname)
            if p:
                error_message = "{}: {}".format(p, error_message)
            raise LoadError(LoadErrorReason.UNRESOLVED_VARIABLE, error_message) from e

    # _resolve_value_expression()
    #
    # Resolves a value expression with the expectation that all
    # variables within this value expression have already been
    # resolved and updated in the Variables._values table.
    #
    # This is used as a part of the iterative resolution codepath,
    # where value expressions are first sorted by dependency before
    # being resolved in one go.
    #
    # Args:
    #    value_expression (list): The value expression to resolve
    #
    # Returns:
    #    (str): The resolved value expression
    #
    def _resolve_value_expression(self, value_expression):
        acc = []

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
# Args:
#    referee (str): The name of the referring variable
#    value_expression (list): The parsed value expression to be expanded
#    parent (ResolutionStep): The parent ResolutionStep
#
class ResolutionStep:

    def __init__(self, referee, value_expression, parent):
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
    def check_circular(self, original_values):
        step = self.parent
        while step:
            if self.referee is step.referee:
                self._raise_circular_reference_error(step, original_values)
            step = step.parent

    # _raise_circular_reference_error()
    #
    # Helper function to construct a full report and raise the LoadError
    # with LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE.
    #
    # Args:
    #    conflict (ResolutionStep): The resolution step which conflicts with this step
    #    original_values (MappingNode): The original node to extract provenances from
    #
    # Raises:
    #    (LoadError): Unconditionally
    #
    def _raise_circular_reference_error(self, conflict, original_values):
        error_lines = []
        step = self

        while step is not conflict:
            if step.parent:
                referee = step.parent.referee
            else:
                referee = self.referee

            provenance = _yaml.node_get_provenance(original_values, referee)
            error_lines.append("{}: Variable '{}' refers to variable '{}'".format(provenance, referee, step.referee))
            step = step.parent

        raise LoadError(LoadErrorReason.CIRCULAR_REFERENCE_VARIABLE,
                        "Circular dependency detected on variable '{}'".format(self.referee),
                        detail="\n".join(reversed(error_lines)))


# _parse_value_expression()
#
# Tries to fetch the parsed value expression from the cache, parsing and
# caching value expressions on demand and returns the parsed value expression.
#
# Args:
#    value_expression (str): The value expression in string form to parse
#
# Returns:
#    (list): The parsed value expression in list form.
#
def _parse_value_expression(value_expression):

    try:
        return VALUE_EXPRESSION_CACHE[value_expression]
    except KeyError:
        # This use of the regex turns a string like "foo %{bar} baz" into
        # a list ["foo ", "bar", " baz"]
        #
        # The result is a parsed value expression, where even indicies
        # contain literal parts of the value and odd indices contain
        # variable names which need to be replaced by resolved variables.
        #
        splits = VALUE_EXPRESSION_REGEX.split(value_expression)

        # Optimize later routines by discarding any unnecessary trailing
        # empty strings.
        #
        if splits[-1] == '':
            del splits[-1]

        # We intern the string parts to try and reduce the memory impact
        # of the cache.
        #
        ret = [sys.intern(s) for s in splits]

        # Cache and return the value expression
        #
        VALUE_EXPRESSION_CACHE[value_expression] = ret
        return ret


# Iterator for all flatten variables.
# Used by Variables.__iter__
class _VariablesIterator:

    def __init__(self, variables):
        self._variables = variables
        self._iter = iter(variables._values)

    def __iter__(self):
        return self

    def __next__(self):
        name = next(self._iter)
        return name, self._variables._expand_var(name)
