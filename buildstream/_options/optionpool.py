#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
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
#
import ast
import jinja2
from collections import Mapping

from .. import _yaml
from .._exceptions import LoadError, LoadErrorReason
from .optionbool import OptionBool
from .optionenum import OptionEnum
from .optionflags import OptionFlags
from .optioneltmask import OptionEltMask
from .optionarch import OptionArch


OPTION_TYPES = {
    OptionBool.OPTION_TYPE: OptionBool,
    OptionEnum.OPTION_TYPE: OptionEnum,
    OptionFlags.OPTION_TYPE: OptionFlags,
    OptionEltMask.OPTION_TYPE: OptionEltMask,
    OptionArch.OPTION_TYPE: OptionArch,
}


class OptionPool():

    def __init__(self, element_path):
        self.options = {}      # The Options
        self.variables = None  # The Options resolved into typed variables

        # We hold on to the element path for the sake of OptionEltMask
        self.element_path = element_path

        # jinja2 environment, with default globals cleared out of the way
        self.environment = jinja2.Environment(undefined=jinja2.StrictUndefined)
        self.environment.globals = []

    # load()
    #
    # Loads the options described in the project.conf
    #
    # Args:
    #    node (dict): The loaded YAML options
    #
    def load(self, options):

        for option_name, option_definition in _yaml.node_items(options):
            opt_type_name = _yaml.node_get(option_definition, str, 'type')

            try:
                opt_type = OPTION_TYPES[opt_type_name]
            except KeyError:
                p = _yaml.node_get_provenance(option_definition, 'type')
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Invalid option type '{}'".format(p, opt_type_name))

            option = opt_type(option_name, option_definition, self)
            self.options[option_name] = option

    # load_values()
    #
    # Loads the option values specified in a key/value
    # dictionary loaded from YAML, and a list of tuples
    # collected from the command line
    #
    # Args:
    #    node (dict): The loaded YAML options
    #    cli_options (list): A list of (str, str) tuples
    #
    def load_values(self, node, cli_options):
        for option_name, _ in _yaml.node_items(node):
            try:
                option = self.options[option_name]
            except KeyError as e:
                p = _yaml.node_get_provenance(node, option_name)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Unknown option '{}' specified".format(p, option_name))
            option.load_value(node)

        for option_name, option_value in cli_options:
            try:
                option = self.options[option_name]
            except KeyError as e:
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "Unknown option '{}' specified on the command line".format(option_name))
            option.set_value(option_value)

    # resolve()
    #
    # Resolves the loaded options, this is just a step which must be
    # performed after loading all options and their values, and before
    # ever trying to evaluate an expression
    #
    def resolve(self):
        self.variables = {}
        for option_name, option in self.options.items():
            # Delegate one more method for options to
            # do some last minute validation once any
            # overrides have been performed.
            #
            option.resolve()

            self.variables[option_name] = option.value

    # evaluate()
    #
    # Evaluates a jinja2 style expression with the loaded options in context.
    #
    # Args:
    #    expression (str): The jinja2 style expression
    #
    # Returns:
    #    (bool): Whether the expression resolved to a truthy value or a falsy one.
    #
    # Raises:
    #    LoadError: If the expression failed to resolve for any reason
    #
    def evaluate(self, expression):

        #
        # Variables must be resolved at this point.
        #
        try:
            template_string = "{%% if %s %%} True {%% else %%} False {%% endif %%}" % expression
            template = self.environment.from_string(template_string)
            context = template.new_context(self.variables, shared=True)
            result = template.root_render_func(context)
            evaluated = jinja2.utils.concat(result)
            val = evaluated.strip()

            if val == "True":
                return True
            elif val == "False":
                return False
            else:  # pragma: nocover
                raise LoadError(LoadErrorReason.EXPRESSION_FAILED,
                                "Failed to evaluate expression: {}".format(expression))
        except jinja2.exceptions.TemplateError as e:
            raise LoadError(LoadErrorReason.EXPRESSION_FAILED,
                            "Failed to evaluate expression ({}): {}".format(expression, e))

    # process_node()
    #
    # Args:
    #    node (Mapping): A YAML Loaded dictionary
    #
    def process_node(self, node):

        # A conditional will result in composition, which can
        # in turn add new conditionals to the root.
        #
        # Keep processing conditionals on the root node until
        # all directly nested conditionals are resolved.
        #
        while self.process_one_node(node):
            pass

        # Now recurse into nested dictionaries and lists
        # and process any indirectly nested conditionals.
        #
        for key, value in _yaml.node_items(node):
            if isinstance(value, Mapping):
                self.process_node(value)
            elif isinstance(value, list):
                self.process_list(value)

    # Recursion assistent for lists, in case there
    # are lists of lists.
    #
    def process_list(self, values):
        for value in values:
            if isinstance(value, Mapping):
                self.process_node(value)
            elif isinstance(value, list):
                self.process_list(value)

    # Process a single conditional, resulting in composition
    # at the root level on the passed node
    #
    # Return true if a conditional was processed.
    #
    def process_one_node(self, node):
        conditions = _yaml.node_get(node, list, '(?)', default_value=[]) or None
        assertion = _yaml.node_get(node, str, '(!)', default_value='') or None

        # Process assersions first, we want to abort on the first encountered
        # assertion in a given dictionary, and not lose an assertion due to
        # it being overwritten by a later assertion which might also trigger.
        if assertion is not None:
            p = _yaml.node_get_provenance(node, '(!)')
            raise LoadError(LoadErrorReason.USER_ASSERTION,
                            "{}: {}".format(p, assertion.strip()))

        if conditions is not None:

            # Collect provenance first, we need to delete the (?) key
            # before any composition occurs.
            provenance = [
                _yaml.node_get_provenance(node, '(?)', indices=[i])
                for i in range(len(conditions))
            ]
            del node['(?)']

            for condition, p in zip(conditions, provenance):
                tuples = list(_yaml.node_items(condition))
                if len(tuples) > 1:
                    raise LoadError(LoadErrorReason.INVALID_DATA,
                                    "{}: Conditional statement has more than one key".format(p))

                expression, value = tuples[0]
                try:
                    if self.evaluate(expression):
                        _yaml.composite(node, value)
                except LoadError as e:
                    # Prepend the provenance of the error
                    raise LoadError(e.reason, "{}: {}".format(p, e)) from e

            return True

        return False
