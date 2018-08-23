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
import os
import click

from .app import App


# This trick is currently only supported on some terminals,
# avoid using it where it can cause garbage to be printed
# to the terminal.
#
def _osc_777_supported():

    term = os.environ.get('TERM')

    if term and (term.startswith('xterm') or term.startswith('vte')):

        # Since vte version 4600, upstream silently ignores
        # the OSC 777 without printing garbage to the terminal.
        #
        # For distros like Fedora who have patched vte, this
        # will trigger a desktop notification and bring attention
        # to the terminal.
        #
        vte_version = os.environ.get('VTE_VERSION')
        try:
            vte_version_int = int(vte_version)
        except (ValueError, TypeError):
            return False

        if vte_version_int >= 4600:
            return True

    return False


# A linux specific App implementation
#
class LinuxApp(App):

    def notify(self, title, text):

        # Currently we only try this notification method
        # of sending an escape sequence to the terminal
        #
        if _osc_777_supported():
            click.echo("\033]777;notify;{};{}\007".format(title, text), err=True)
