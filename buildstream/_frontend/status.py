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
import datetime
import click
from blessings import Terminal

# Import a widget internal for formatting time codes
from .widget import TimeCode


# Status()
#
# A widget for formatting overall status.
#
# Note that the render() and clear() methods in this class are
# simply noops in the case that the application is not connected
# to a terminal, or if the terminal does not support ANSI escape codes.
#
# Args:
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#
class Status():

    def __init__(self, content_profile, format_profile):

        self.content_profile = content_profile
        self.format_profile = format_profile
        self.jobs = []
        self.last_lines = 0  # Number of status lines we last printed to console
        self.term = Terminal()
        self.spacing = 1

        self.term_width, _ = click.get_terminal_size()
        self.alloc_lines = 0
        self.alloc_columns = None
        self.line_length = 0
        self.need_alloc = True

    # add_job()
    #
    # Adds a job to track in the status area
    #
    # Args:
    #    element (Element): The element of the job to track
    #    action_name (str): The action name for this job
    #
    def add_job(self, element, action_name):
        job = StatusJob(element, action_name, self.content_profile, self.format_profile)
        self.jobs.append(job)
        self.need_alloc = True

    # remove_job()
    #
    # Removes a job currently being tracked in the status area
    #
    # Args:
    #    element (Element): The element of the job to track
    #    action_name (str): The action name for this job
    #
    def remove_job(self, element, action_name):
        self.jobs = [
            job for job in self.jobs
            if not (job.element is element and
                    job.action_name == action_name)
        ]
        self.need_alloc = True

    # clear()
    #
    # Clear the status area, it is necessary to call
    # this before printing anything to the console if
    # a status area is in use.
    #
    # To print some logging to the output and then restore
    # the status, use the following:
    #
    #   status.clear()
    #   ... print something to console ...
    #   status.render()
    #
    def clear(self):

        if not self.term.does_styling:
            return

        for i in range(self.last_lines):
            self.move_up()
            self.clear_line()
        self.last_lines = 0

    # render()
    #
    # Render the status area.
    #
    # If you are not printing a line in addition to rendering
    # the status area, for instance in a timeout, then it is
    # not necessary to call clear().
    def render(self):

        if not self.term.does_styling:
            return

        self.clear()
        self.check_term_width()
        self.allocate()

        # Nothing to render, early return
        if self.alloc_lines == 0:
            return

        # Before rendering the actual lines, we need to add some line
        # feeds for the amount of lines we intend to print first, and
        # move cursor position back to the first line
        for _ in range(self.alloc_lines + 1):
            click.echo('')
        for _ in range(self.alloc_lines + 1):
            self.move_up()

        # Print one separator line
        separator = self.format_profile.fmt('=' * self.line_length)
        click.echo(separator)

        # Now we have the number of columns, and an allocation for
        # alignment of each column
        n_columns = len(self.alloc_columns)
        for line in self.job_lines(n_columns):
            text = ''
            for job in line:
                column = line.index(job)
                text += job.render(self.alloc_columns[column] - job.size)

                # Add padding for columnization
                # text += ' ' * (self.alloc_columns[column] - job.size)

                # Add spacing between columns
                if column < (n_columns - 1):
                    text += ' ' * self.spacing

            # Print the line
            click.echo(text)

        # Track what we printed last, for the next clear
        self.last_lines = self.alloc_lines + 1

    ###########################################
    #         Status area internals           #
    ###########################################
    def check_term_width(self):
        term_width, _ = click.get_terminal_size()
        if self.term_width != term_width:
            self.term_width = term_width
            self.need_alloc = True

    def move_up(self):
        # Explicitly move to beginning of line, fixes things up
        # when there was a ^C or ^Z printed to the terminal.
        click.echo(self.term.move_x(0) + self.term.move_up, nl=False)

    def clear_line(self):
        click.echo(self.term.clear_eol, nl=False)

    def allocate(self):
        if not self.need_alloc:
            return

        # State when there is no jobs to display
        alloc_lines = 0
        alloc_columns = []
        line_length = 0

        # Test for the widest width which fits columnized jobs
        for columns in reversed(range(len(self.jobs))):
            alloc_lines, alloc_columns = self.allocate_columns(columns + 1)

            # If the sum of column widths with spacing in between
            # fits into the terminal width, this is a good allocation.
            line_length = sum(alloc_columns) + (columns * self.spacing)
            if line_length < self.term_width:
                break

        self.alloc_lines = alloc_lines
        self.alloc_columns = alloc_columns
        self.line_length = line_length
        self.need_alloc = False

    def job_lines(self, columns):
        for i in range(0, len(self.jobs), columns):
            yield self.jobs[i:i + columns]

    # Returns an array of integers representing the maximum
    # length in characters for each column, given the current
    # list of jobs to render.
    #
    def allocate_columns(self, columns):
        column_widths = [0 for _ in range(columns)]
        lines = 0
        for line in self.job_lines(columns):
            line_len = len(line)
            lines += 1
            for col in range(columns):
                if (col < line_len):
                    job = line[col]
                    column_widths[col] = max(column_widths[col], job.size)

        return lines, column_widths


# A widget for formatting a job in the status area
class StatusJob():

    def __init__(self, element, action_name, content_profile, format_profile):
        # Record start time at initialization
        self.starttime = datetime.datetime.now()
        self.element = element
        self.action_name = action_name
        self.content_profile = content_profile
        self.format_profile = format_profile
        self.time_code = TimeCode(content_profile, format_profile)

        # Calculate the size needed to display
        self.size = 10  # Size of time code
        self.size += len(action_name)
        self.size += len(element._get_display_name())
        self.size += 3  # '[' + ':' + ']'

    # render()
    #
    # Render the Job, return a rendered string
    #
    # Args:
    #    padding (int): Amount of padding to print in order to align with columns
    #
    def render(self, padding):
        elapsed = datetime.datetime.now() - self.starttime
        text = self.time_code.render_time(elapsed)

        # Add padding after the display name, before terminating ']'
        display_name = self.element._get_display_name() + (' ' * padding)
        text += self.format_profile.fmt('[') + \
            self.content_profile.fmt(self.action_name) + \
            self.format_profile.fmt(':') + \
            self.content_profile.fmt(display_name) + \
            self.format_profile.fmt(']')

        return text
