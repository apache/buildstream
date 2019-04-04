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

import re
import sys

from ._exceptions import LoadError, LoadErrorReason
from . import _yaml

# Variables are allowed to have dashes here
#
PARSE_EXPANSION = re.compile(r"\%\{([a-zA-Z][a-zA-Z0-9_-]*)\}")


# Throughout this code you will see variables named things like `expstr`.
# These hold data structures called "expansion strings" and are the parsed
# form of the strings which are the input to this subsystem.  Strings
# such as "Hello %{name}, how are you?" are parsed into the form:
# (3, ["Hello ", "name", ", how are you?"])
# i.e. a tuple of an integer and a list, where the integer is the cached
# length of the list, and the list consists of one or more strings.
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
#     node (dict): A node loaded and composited with yaml tools
#
# Raises:
#     LoadError, if unresolved variables, or cycles in resolution, occur.
#
class Variables():

    def __init__(self, node):

        self.original = node
        self._expstr_map = self._resolve(node)
        self.flat = self._flatten()

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
    def subst(self, string):
        expstr = _parse_expstr(string)

        try:
            return _expand_expstr(self._expstr_map, expstr)
        except KeyError:
            unmatched = []

            # Look for any unmatched variable names in the expansion string
            for var in expstr[1][1::2]:
                if var not in self._expstr_map:
                    unmatched.append(var)

            if unmatched:
                message = "Unresolved variable{}: {}".format(
                    "s" if len(unmatched) > 1 else "",
                    ", ".join(unmatched)
                )

                raise LoadError(LoadErrorReason.UNRESOLVED_VARIABLE, message)
            # Otherwise, re-raise the KeyError since it clearly came from some
            # other unknowable cause.
            raise

    # Variable resolving code
    #
    # Here we resolve all of our inputs into a dictionary, ready for use
    # in subst()
    def _resolve(self, node):
        # Special case, if notparallel is specified in the variables for this
        # element, then override max-jobs to be 1.
        # Initialize it as a string as all variables are processed as strings.
        #
        if _yaml.node_get(node, bool, 'notparallel', default_value=False):
            _yaml.node_set(node, 'max-jobs', str(1))

        ret = {}
        for key, value in _yaml.node_items(node):
            value = _yaml.node_get(node, str, key)
            ret[sys.intern(key)] = _parse_expstr(value)
        return ret

    def _check_for_missing(self):
        # First the check for anything unresolvable
        summary = []
        for key, expstr in self._expstr_map.items():
            for var in expstr[1][1::2]:
                if var not in self._expstr_map:
                    line = "  unresolved variable '{unmatched}' in declaration of '{variable}' at: {provenance}"
                    provenance = _yaml.node_get_provenance(self.original, key)
                    summary.append(line.format(unmatched=var, variable=key, provenance=provenance))
        if summary:
            raise LoadError(LoadErrorReason.UNRESOLVED_VARIABLE,
                            "Failed to resolve one or more variable:\n{}\n".format("\n".join(summary)))

    def _check_for_cycles(self):
        # And now the cycle checks
        def cycle_check(expstr, visited, cleared):
            for var in expstr[1][1::2]:
                if var in cleared:
                    continue
                if var in visited:
                    raise LoadError(LoadErrorReason.RECURSIVE_VARIABLE,
                                    "{}: ".format(_yaml.node_get_provenance(self.original, var)) +
                                    ("Variable '{}' expands to contain a reference to itself. " +
                                     "Perhaps '{}' contains '%{{{}}}").format(var, visited[-1], var))
                visited.append(var)
                cycle_check(self._expstr_map[var], visited, cleared)
                visited.pop()
                cleared.add(var)

        cleared = set()
        for key, expstr in self._expstr_map.items():
            if key not in cleared:
                cycle_check(expstr, [key], cleared)

    # _flatten():
    #
    # Turn our dictionary of expansion strings into a flattened dict
    # so that we can run expansions faster in the future
    #
    # Raises:
    #    LoadError, if the string contains unresolved variable references or
    #               if cycles are detected in the variable references
    #
    def _flatten(self):
        flat = {}
        try:
            for key, expstr in self._expstr_map.items():
                if expstr[0] > 1:
                    expstr = (1, [sys.intern(_expand_expstr(self._expstr_map, expstr))])
                    self._expstr_map[key] = expstr
                flat[key] = expstr[1][0]
        except KeyError:
            self._check_for_missing()
            raise
        except RecursionError:
            self._check_for_cycles()
            raise
        return flat


# Cache for the parsed expansion strings.  While this is nominally
# something which might "waste" memory, in reality each of these
# will live as long as the element which uses it, which is the
# vast majority of the memory usage across the execution of BuildStream.
PARSE_CACHE = {
    # Prime the cache with the empty string since otherwise that can
    # cause issues with the parser, complications to which cause slowdown
    "": (1, [""]),
}


# Helper to parse a string into an expansion string tuple, caching
# the results so that future parse requests don't need to think about
# the string
def _parse_expstr(instr):
    try:
        return PARSE_CACHE[instr]
    except KeyError:
        # This use of the regex turns a string like "foo %{bar} baz" into
        # a list ["foo ", "bar", " baz"]
        splits = PARSE_EXPANSION.split(instr)
        # If an expansion ends the string, we get an empty string on the end
        # which we can optimise away, making the expansion routines not need
        # a test for this.
        if splits[-1] == '':
            splits = splits[:-1]
        # Cache an interned copy of this.  We intern it to try and reduce the
        # memory impact of the cache.  It seems odd to cache the list length
        # but this is measurably cheaper than calculating it each time during
        # string expansion.
        PARSE_CACHE[instr] = (len(splits), [sys.intern(s) for s in splits])
        return PARSE_CACHE[instr]


# Helper to expand a given top level expansion string tuple in the context
# of the given dictionary of expansion strings.
#
# Note: Will raise KeyError if any expansion is missing
def _expand_expstr(content, topvalue):
    # Short-circuit constant strings
    if topvalue[0] == 1:
        return topvalue[1][0]

    # Short-circuit strings which are entirely an expansion of another variable
    # e.g. "%{another}"
    if topvalue[0] == 2 and topvalue[1][0] == "":
        return _expand_expstr(content, content[topvalue[1][1]])

    # Otherwise process fully...
    def internal_expand(value):
        (expansion_len, expansion_bits) = value
        idx = 0
        while idx < expansion_len:
            # First yield any constant string content
            yield expansion_bits[idx]
            idx += 1
            # Now, if there is an expansion variable left to expand, yield
            # the expansion of that variable too
            if idx < expansion_len:
                yield from internal_expand(content[expansion_bits[idx]])
            idx += 1

    return "".join(internal_expand(topvalue))
