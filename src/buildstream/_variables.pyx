#
#  Copyright (C) 2016 Codethink Limited
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

from ._exceptions import LoadError
from .exceptions import LoadErrorReason
from .node cimport MappingNode, Node, ScalarNode, SequenceNode

# Variables are allowed to have dashes here
#
PARSE_EXPANSION = re.compile(r"\%\{([a-zA-Z][a-zA-Z0-9_-]*)\}")


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
# To see how strings are parsed, see `_parse_expstr()` after the class, and
# to see how expansion strings are expanded, see `_expand_expstr()` after that.


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

    cdef MappingNode original
    cdef dict _expstr_map

    def __init__(self, MappingNode node):
        self.original = node
        self._expstr_map = self._resolve(node)
        self._check_for_missing()
        self._check_for_cycles()

    def __getitem__(self, str name):
        return _expand_var(self._expstr_map, name)

    def __contains__(self, str name):
        return name in self._expstr_map

    # __iter__()
    #
    # Provide an iterator for all variables effective values
    #
    # Returns:
    #   (Iterator[Tuple[str, str]])
    #
    def __iter__(self):
        return _VariablesIterator(self._expstr_map)

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
        if name not in self._expstr_map:
            return None
        return _expand_var(self._expstr_map, name)

    # expand()
    #
    # Expand all the variables found in the given Node, recursively.
    # This does the change in place, modifying the node. If you want to keep
    # the node untouched, you should use `node.clone()` beforehand
    #
    # Args:
    #   (Node): A node for which to substitute the values
    #
    cpdef expand(self, Node node):
        if isinstance(node, ScalarNode):
            (<ScalarNode> node).value = self.subst((<ScalarNode> node).value)
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
    #    (string): The string to substitute
    #
    # Returns:
    #    (string): The new string with any substitutions made
    #
    # Raises:
    #    LoadError, if the string contains unresolved variable references.
    #
    cpdef subst(self, str string):
        expstr = _parse_expstr(string)

        try:
            return _expand_expstr(self._expstr_map, expstr)
        except KeyError:
            unmatched = []

            # Look for any unmatched variable names in the expansion string
            for var in expstr[1::2]:
                if var not in self._expstr_map:
                    unmatched.append(var)

            if unmatched:
                message = "Unresolved variable{}: {}".format(
                    "s" if len(unmatched) > 1 else "",
                    ", ".join(unmatched)
                )

                raise LoadError(message, LoadErrorReason.UNRESOLVED_VARIABLE)
            # Otherwise, re-raise the KeyError since it clearly came from some
            # other unknowable cause.
            raise

    # Variable resolving code
    #
    # Here we resolve all of our inputs into a dictionary, ready for use
    # in subst()
    cdef dict _resolve(self, MappingNode node):
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
            ret[sys.intern(key)] = _parse_expstr(value)
        return ret

    def _check_for_missing(self):
        # First the check for anything unresolvable
        summary = []
        for key, expstr in self._expstr_map.items():
            for var in expstr[1::2]:
                if var not in self._expstr_map:
                    line = "  unresolved variable '{unmatched}' in declaration of '{variable}' at: {provenance}"
                    provenance = self.original.get_scalar(key).get_provenance()
                    summary.append(line.format(unmatched=var, variable=key, provenance=provenance))
        if summary:
            raise LoadError("Failed to resolve one or more variable:\n{}\n".format("\n".join(summary)),
                            LoadErrorReason.UNRESOLVED_VARIABLE)

    def _check_for_cycles(self):
        # And now the cycle checks
        def cycle_check(expstr, visited, cleared):
            for var in expstr[1::2]:
                if var in cleared:
                    continue
                if var in visited:
                    raise LoadError("{}: ".format(self.original.get_scalar(var).get_provenance()) +
                                    ("Variable '{}' expands to contain a reference to itself. " +
                                     "Perhaps '{}' contains '%{{{}}}").format(var, visited[-1], var),
                                     LoadErrorReason.RECURSIVE_VARIABLE)
                visited.append(var)
                cycle_check(self._expstr_map[var], visited, cleared)
                visited.pop()
                cleared.add(var)

        cleared = set()
        for key, expstr in self._expstr_map.items():
            if key not in cleared:
                cycle_check(expstr, [key], cleared)

# Cache for the parsed expansion strings.  While this is nominally
# something which might "waste" memory, in reality each of these
# will live as long as the element which uses it, which is the
# vast majority of the memory usage across the execution of BuildStream.
cdef dict PARSE_CACHE = {
    # Prime the cache with the empty string since otherwise that can
    # cause issues with the parser, complications to which cause slowdown
    "": [""],
}


# Helper to parse a string into an expansion string tuple, caching
# the results so that future parse requests don't need to think about
# the string
cdef list _parse_expstr(str instr):
    cdef list ret

    try:
        return <list> PARSE_CACHE[instr]
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
        PARSE_CACHE[instr] = ret
        return ret


# Helper to expand and cache a variable definition in the context of
# the given dictionary of expansion strings.
#
# Args:
#     content (dict): Dictionary of expansion strings
#     name (str): Name of the variable to expand
#     counter (int): Recursion counter
#
# Returns:
#     (str): The expanded value of variable
#
# Raises:
#     KeyError, if any expansion is missing
#     RecursionError, if recursion required for evaluation is too deep
#
cdef str _expand_var(dict content, str name, int counter = 0):
    cdef str sub

    if len(content[name]) > 1:
        sub = _expand_expstr(content, <list> content[name], counter)
        content[name] = [sys.intern(sub)]

    return content[name][0]


# Helper to expand a given top level expansion string tuple in the context
# of the given dictionary of expansion strings.
#
# Args:
#     content (dict): Dictionary of expansion strings
#     name (str): Name of the variable to expand
#     counter (int): Recursion counter
#
# Returns:
#     (str): The expanded value of variable
#
# Raises:
#     KeyError, if any expansion is missing
#     RecursionError, if recursion required for evaluation is too deep
#
cdef str _expand_expstr(dict content, list value, int counter = 0):
    if counter > 1000:
        raise RecursionError()

    cdef Py_ssize_t idx = 0
    cdef Py_ssize_t value_len = len(value)
    cdef str sub
    cdef list acc = []

    while idx < value_len:
        acc.append(value[idx])
        idx += 1

        if idx < value_len:
            acc.append(_expand_var(content, <str> value[idx], counter + 1))
        idx += 1

    return "".join(acc)


# Iterator for all flatten variables.
# Used by Variables.__iter__
cdef class _VariablesIterator:
    cdef dict _expstr_map
    cdef object _iter

    def __init__(self, dict expstr_map):
        self._expstr_map = expstr_map
        self._iter = iter(expstr_map)

    def __iter__(self):
        return self

    def __next__(self):
        name = next(self._iter)
        return name, _expand_var(self._expstr_map, name)
