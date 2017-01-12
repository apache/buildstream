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

import re


# Text formatting for the console
#
# Note that because we use click, the output we send to the terminal
# with click.echo() will be stripped of ansi control unless displayed
# on the console to the user (there are also some compatibility features
# for text formatting on windows)
#
class Color():
    BLACK = "30"
    RED = "31"
    GREEN = "32"
    YELLOW = "33"
    BLUE = "34"
    MAGENTA = "35"
    CYAN = "36"
    WHITE = "37"


class Attr():
    CLEAR = "0"
    BOLD = "1"
    DARK = "2"
    ITALIC = "3"
    UNDERLINE = "4"
    BLINK = "5"
    REVERSE_VIDEO = "7"
    CONCEALED = "8"


# fmt()
#
# Formats text with Color and Attr attributes, so that
# the returned text contains ansi control sequences telling
# the terminal how to display the text.
#
# Args:
#    text (str): The text to format
#    color (Color): The color, if any
#    attrs (list): A list of Attr values, if any
#
# Note that these control sequences are stripped from output
# automatically by click.echo() when BuildStream is not connected
# to the terminal.
#
def fmt(text, color=None, attrs=[]):

    if color is None and not attrs:
        return text

    CNTL_START = "\033["
    CNTL_END = "m"
    CNTL_SEPARATOR = ";"

    attr_count = 0

    # Set graphics mode
    new_text = CNTL_START
    for attr in attrs:
        if attr_count > 0:
            new_text += CNTL_SEPARATOR
        new_text += attr
        attr_count += 1

    if color is not None:
        if attr_count > 0:
            new_text += CNTL_SEPARATOR
        new_text += color
        attr_count += 1

    new_text += CNTL_END

    # Add text
    new_text += text

    # Clear graphics mode settings
    new_text += (CNTL_START + Attr.CLEAR + CNTL_END)

    return new_text


# fmt_subst()
#
# Like fmt(), but can be used to format and substitute python formatting
# strings prefixed with %.
#
# Args:
#    text (str): The text to format
#    varname (str): Name of the token to substitute
#    value (str): Value to place for the token
#    color (Color): The color for the value, if any
#    attrs (list): A list of Attr values for the value, if any
#
# This will first center the %{name} in a 20 char width
# and format the %{name} in blue.
#
#    formatted = format_symbol("This is your %{name: ^20}", "name", "Bob", color=Color.BLUE)
#
# We use this because python formatting methods which use
# padding will consider the ansi escape sequences we use.
#
def fmt_subst(text, varname, value, color=None, attrs=[]):

    def subst_callback(match):
        # Extract and format the "{(varname)...}" portion of the match
        inner_token = match.group(1)
        formatted = inner_token.format(**{varname: value})

        # Colorize after the pythonic format formatting, which may have padding
        return fmt(formatted, color, attrs)

    # Lazy regex, after our word, match anything that does not have '%'
    return re.sub(r"%(\{(" + varname + r")[^%]*\})", subst_callback, text)
