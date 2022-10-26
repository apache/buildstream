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
class Profile:
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
        return re.sub(r"%(\{(" + varname + r")[^%]*?\})", subst_callback, text)
