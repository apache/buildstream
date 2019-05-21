#
#  Copyright (C) 2018 Codethink Limited
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
import copy
import click


# Profile()
#
# A class for formatting text with ansi color codes
#
# Kwargs:
#    The same keyword arguments which can be used with click.style()
#
class Profile():
    def __init__(self, **kwargs):
        self._kwargs = dict(kwargs)

    # fmt()
    #
    # Format some text with ansi color codes
    #
    # Args:
    #    text (str): The text to format
    #
    # Kwargs:
    #    Keyword arguments to apply on top of the base click.style()
    #    arguments
    #
    def fmt(self, text, **kwargs):
        kwargs = dict(kwargs)
        fmtargs = copy.copy(self._kwargs)
        fmtargs.update(kwargs)
        return click.style(text, **fmtargs)

    # fmt_subst()
    #
    # Substitute a variable of the %{varname} form, formatting
    # only the substituted text with the given click.style() configurations
    #
    # Args:
    #    text (str): The text to format, with possible variables
    #    varname (str): The variable name to substitute
    #    value (str): The value to substitute the variable with
    #
    # Kwargs:
    #    Keyword arguments to apply on top of the base click.style()
    #    arguments
    #
    def fmt_subst(self, text, varname, value, **kwargs):

        def subst_callback(match):
            # Extract and format the "{(varname)...}" portion of the match
            inner_token = match.group(1)
            formatted = inner_token.format(**{varname: value})

            # Colorize after the pythonic format formatting, which may have padding
            return self.fmt(formatted, **kwargs)

        # Lazy regex, after our word, match anything that does not have '%'
        return re.sub(r"%(\{(" + varname + r")[^%]*\})", subst_callback, text)
