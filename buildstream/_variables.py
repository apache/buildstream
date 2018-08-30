#
#  Copyright (C) 2016 Codethink Limited
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

import re

from ._exceptions import LoadError, LoadErrorReason
from . import _yaml

# Variables are allowed to have dashes here
#
_VARIABLE_MATCH = r'\%\{([a-zA-Z][a-zA-Z0-9_-]*)\}'


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
#     LoadError, if unresolved variables occur.
#
class Variables():

    def __init__(self, node):

        self.original = node
        self.variables = self._resolve(node)

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
        substitute, unmatched, _ = self._subst(string, self.variables)
        unmatched = list(set(unmatched))
        if unmatched:
            if len(unmatched) == 1:
                message = "Unresolved variable '{var}'".format(var=unmatched[0])
            else:
                message = "Unresolved variables: "
                for unmatch in unmatched:
                    if unmatched.index(unmatch) > 0:
                        message += ', '
                    message += unmatch

            raise LoadError(LoadErrorReason.UNRESOLVED_VARIABLE, message)

        return substitute

    def _subst(self, string, variables):

        def subst_callback(match):
            nonlocal variables
            nonlocal unmatched
            nonlocal matched

            token = match.group(0)
            varname = match.group(1)

            value = _yaml.node_get(variables, str, varname, default_value=None)
            if value is not None:
                # We have to check if the inner string has variables
                # and return unmatches for those
                unmatched += re.findall(_VARIABLE_MATCH, value)
                matched += [varname]
            else:
                # Return unmodified token
                unmatched += [varname]
                value = token

            return value

        matched = []
        unmatched = []
        replacement = re.sub(_VARIABLE_MATCH, subst_callback, string)

        return (replacement, unmatched, matched)

    # Variable resolving code
    #
    # Here we substitute variables for values (resolve variables) repeatedly
    # in a dictionary, each time creating a new dictionary until there is no
    # more unresolved variables to resolve, or, until resolving further no
    # longer resolves anything, in which case we throw an exception.
    def _resolve(self, node):
        variables = node

        # Special case, if notparallel is specified in the variables for this
        # element, then override max-jobs to be 1.
        # Initialize it as a string as all variables are processed as strings.
        #
        if _yaml.node_get(variables, bool, 'notparallel', default_value=False):
            variables['max-jobs'] = str(1)

        # Resolve the dictionary once, reporting the new dictionary with things
        # substituted in it, and reporting unmatched tokens.
        #
        def resolve_one(variables):
            unmatched = []
            resolved = {}

            for key, value in _yaml.node_items(variables):

                # Ensure stringness of the value before substitution
                value = _yaml.node_get(variables, str, key)

                resolved_var, item_unmatched, matched = self._subst(value, variables)

                if _wrap_variable(key) in resolved_var:
                    referenced_through = find_recursive_variable(key, matched, variables)
                    raise LoadError(LoadErrorReason.RECURSIVE_VARIABLE,
                                    "{}: ".format(_yaml.node_get_provenance(variables, key)) +
                                    ("Variable '{}' expands to contain a reference to itself. " +
                                     "Perhaps '{}' contains '{}").format(key, referenced_through, _wrap_variable(key)))

                resolved[key] = resolved_var
                unmatched += item_unmatched

            # Carry over provenance
            resolved[_yaml.PROVENANCE_KEY] = variables[_yaml.PROVENANCE_KEY]
            return (resolved, unmatched)

        # Resolve it until it's resolved or broken
        #
        resolved = variables
        unmatched = ['dummy']
        last_unmatched = ['dummy']
        while unmatched:
            resolved, unmatched = resolve_one(resolved)

            # Lists of strings can be compared like this
            if unmatched == last_unmatched:
                # We've got the same result twice without matching everything,
                # something is undeclared or cyclic, compose a summary.
                #
                summary = ''
                for unmatch in set(unmatched):
                    for var, provenance in self._find_references(unmatch):
                        line = "  unresolved variable '{unmatched}' in declaration of '{variable}' at: {provenance}\n"
                        summary += line.format(unmatched=unmatch, variable=var, provenance=provenance)

                raise LoadError(LoadErrorReason.UNRESOLVED_VARIABLE,
                                "Failed to resolve one or more variable:\n{}".format(summary))

            last_unmatched = unmatched

        return resolved

    # Helper function to fetch information about the node referring to a variable
    #
    def _find_references(self, varname):
        fullname = _wrap_variable(varname)
        for key, value in _yaml.node_items(self.original):
            if fullname in value:
                provenance = _yaml.node_get_provenance(self.original, key)
                yield (key, provenance)


def find_recursive_variable(variable, matched_variables, all_vars):
    matched_values = (_yaml.node_get(all_vars, str, key) for key in matched_variables)
    for key, value in zip(matched_variables, matched_values):
        if _wrap_variable(variable) in value:
            return key
    else:
        return None


def _wrap_variable(var):
    return "%{" + var + "}"
