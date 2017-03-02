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

import click
import re
import subprocess
import copy

from . import utils
from .plugin import _plugin_lookup
from ._message import MessageType
from . import ImplError
from . import Element, Scope


# Profile()
#
# A class for formatting text with ansi color codes
#
# Kwargs:
#    The same keyword arguments which can be used with click.style()
#
class Profile():
    def __init__(self, **kwargs):
        self.kwargs = dict(kwargs)

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
        fmtargs = copy.copy(self.kwargs)
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


# Widget()
#
# Args:
#    content_profile (Profile): The profile to use for rendering content
#    format_profile (Profile): The profile to use for rendering formatting
#
# An abstract class for printing output columns in our text UI.
#
class Widget():

    def __init__(self, content_profile, format_profile):

        # The content profile
        self.content_profile = content_profile

        # The formatting profile
        self.format_profile = format_profile

    # size_request()
    #
    # Gives the widget a chance to preflight the pipeline
    # and figure out what size it might need for alignment purposes
    #
    # Args:
    #    pipeline (Pipeline): The pipeline to process
    #
    def size_request(self, pipeline):
        pass

    # render()
    #
    # Renders a string to be printed in the UI
    #
    # Args:
    #    message (Message): A message to print
    #
    # Returns:
    #    (str): The string this widget prints for the given message
    #
    def render(self, message):
        raise ImplError("{} does not implement render()".format(type(self).__name__))


# Used to add spacing between columns
class Space(Widget):

    def render(self, message):
        return ' '


# A widget for rendering the debugging column
class Debug(Widget):

    def render(self, message):
        unique_id = 0 if message.unique_id is None else message.unique_id

        text = self.format_profile.fmt('[pid:')
        text += self.content_profile.fmt("{: <5}".format(message.pid))
        text += self.format_profile.fmt(" id:")
        text += self.content_profile.fmt("{:0>3}".format(unique_id))
        text += self.format_profile.fmt(']')

        return text


# A widget for rendering the time codes
class TimeCode(Widget):

    def render(self, message):
        if message.elapsed is None:
            fields = [
                self.content_profile.fmt('--')
                for i in range(3)
            ]
        else:
            hours, remainder = divmod(int(message.elapsed.total_seconds()), 60 * 60)
            minutes, seconds = divmod(remainder, 60)
            fields = [
                self.content_profile.fmt("{0:02d}".format(field))
                for field in [hours, minutes, seconds]
            ]

        return self.format_profile.fmt('[') + \
            self.format_profile.fmt(':').join(fields) + \
            self.format_profile.fmt(']')


# A widget for rendering the action name
class ActionName(Widget):

    def render(self, message):
        action_name = message.action_name
        if not action_name:
            action_name = ""
        return self.format_profile.fmt('[') + \
            self.content_profile.fmt("{: ^5}".format(action_name)) + \
            self.format_profile.fmt(']')


# A widget for rendering the MessageType
class TypeName(Widget):

    action_colors = {
        MessageType.DEBUG: "cyan",
        MessageType.STATUS: "cyan",
        MessageType.INFO: "magenta",
        MessageType.WARN: "yellow",
        MessageType.ERROR: "red",
        MessageType.START: "blue",
        MessageType.SUCCESS: "green",
        MessageType.FAIL: "red",
    }

    def render(self, message):
        return self.content_profile.fmt("{: <7}"
                                        .format(message.message_type.upper()),
                                        bold=True, dim=True,
                                        fg=self.action_colors[message.message_type])


# A widget for displaying the Element name
class ElementName(Widget):

    def __init__(self, content_profile, format_profile):
        super(ElementName, self).__init__(content_profile, format_profile)

        # Pre initialization format string, before we know the length of
        # element names in the pipeline
        self.fmt_string = '{: <35}'

    def size_request(self, pipeline):
        longest_name = 0
        for plugin in pipeline.dependencies(Scope.ALL, include_sources=True):
            longest_name = max(len(plugin._get_display_name()), longest_name)

        # Put a cap at a specific width, usually some elements cause the line
        # to be too long, just live with the unaligned columns in that case
        longest_name = min(longest_name, 35)
        self.fmt_string = '{: <' + str(longest_name) + '}'

    def render(self, message):
        if message.unique_id is not None:
            plugin = _plugin_lookup(message.unique_id)
            name = plugin._get_display_name()
        else:
            name = ''

        return self.format_profile.fmt('[') + \
            self.content_profile.fmt(
                self.fmt_string.format(name)) + \
            self.format_profile.fmt(']')


# A widget for displaying the primary message text
class MessageText(Widget):

    def render(self, message):

        return message.message


# A widget for formatting the element cache key
class CacheKey(Widget):

    def __init__(self, content_profile, format_profile, err_profile):
        super(CacheKey, self).__init__(content_profile, format_profile)

        self.err_profile = err_profile

    def size_request(self, pipeline):
        self.key_length = pipeline.context.log_key_length

    def render(self, message):

        key = ' ' * self.key_length
        if message.unique_id is not None:
            plugin = _plugin_lookup(message.unique_id)
            if isinstance(plugin, Element):
                key = plugin._get_display_key()

        if message.message_type == MessageType.FAIL:
            text = self.err_profile.fmt(key)
        else:
            text = self.content_profile.fmt(key)

        return self.format_profile.fmt('[') + text + self.format_profile.fmt(']')


# A widget for formatting the log file
class LogFile(Widget):

    def __init__(self, content_profile, format_profile, err_profile):
        super(LogFile, self).__init__(content_profile, format_profile)

        self.err_profile = err_profile
        self.logdir = ''

    def size_request(self, pipeline):

        # Hold on to the logging directory so we can abbreviate
        self.logdir = pipeline.context.logdir

    def render(self, message):

        if message.logfile and message.scheduler:
            logfile = message.logfile
            if logfile.startswith(self.logdir):
                logfile = logfile[len(self.logdir) + 1:]

            if message.message_type == MessageType.FAIL:
                text = self.err_profile.fmt(logfile)
            else:
                text = self.content_profile.fmt(logfile, dim=True)
        else:
            text = ''

        return text


# A widget for formatting a log line
class LogLine(Widget):

    def __init__(self, content_profile, format_profile, err_profile, detail_profile,
                 indent=4,
                 log_lines=10,
                 debug=False):
        super(LogLine, self).__init__(content_profile, format_profile)

        self.columns = []
        self.err_profile = err_profile
        self.detail_profile = detail_profile
        self.indent = ' ' * indent
        self.log_lines = log_lines

        self.space_widget = Space(content_profile, format_profile)
        self.message_widget = MessageText(content_profile, format_profile)
        self.logfile_widget = LogFile(content_profile, format_profile, err_profile)

        if debug:
            self.columns.extend([
                Debug(content_profile, format_profile),
                ActionName(content_profile, format_profile)
            ])

        self.columns.extend([
            TimeCode(content_profile, format_profile),
            CacheKey(content_profile, format_profile, err_profile),
            ElementName(content_profile, format_profile),
            self.space_widget,
            TypeName(content_profile, format_profile),
            self.space_widget
        ])

    def size_request(self, pipeline):
        for widget in self.columns:
            widget.size_request(pipeline)

        self.space_widget.size_request(pipeline)
        self.message_widget.size_request(pipeline)
        self.logfile_widget.size_request(pipeline)

    def render(self, message):

        # Render the column widgets first
        text = ''
        for widget in self.columns:
            text += widget.render(message)

        # Show the action only in the main start/success/fail messages
        if message.scheduler:
            text += self.logfile_widget.render(message)
        else:
            text += self.message_widget.render(message)

        text += '\n'

        extra_nl = False

        # Now add some custom things
        if message.detail is not None:

            detail = message.detail.rstrip('\n')
            detail = self.indent + self.indent.join((detail.splitlines(True)))

            text += '\n'
            if message.message_type == MessageType.FAIL:
                text += self.err_profile.fmt(detail, bold=True)
            else:
                text += self.detail_profile.fmt(detail)
            text += '\n'
            extra_nl = True

        if message.sandbox is not None:
            sandbox = self.indent + 'Sandbox directory: ' + message.sandbox

            text += '\n'
            if message.message_type == MessageType.FAIL:
                text += self.err_profile.fmt(sandbox, bold=True)
            else:
                text += self.detail_profile.fmt(sandbox)
            text += '\n'
            extra_nl = True

        if message.scheduler and message.message_type == MessageType.FAIL:
            log_content = read_last_lines(message.logfile)
            log_content = self.indent + self.indent.join(log_content.splitlines(True))

            text += '\n'
            text += self.detail_profile.fmt(log_content)
            text += '\n'
            extra_nl = True

        if extra_nl:
            text += '\n'

        return text

    def read_last_lines(logfile):
        tail_command = utils.get_host_tool('tail')

        # Lets just expect this to always pass for now...
        output = subprocess.check_output([tail_command, '-n', str(self.log_lines), logfile])
        output = output.decode('UTF-8')
        return output.rstrip()
