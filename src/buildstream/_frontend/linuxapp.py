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
import os
import click

from .app import App


# This trick is currently only supported on some terminals,
# avoid using it where it can cause garbage to be printed
# to the terminal.
#
def _osc_777_supported():

    term = os.environ.get("TERM")

    if term and (term.startswith("xterm") or term.startswith("vte")):

        # Since vte version 4600, upstream silently ignores
        # the OSC 777 without printing garbage to the terminal.
        #
        # For distros like Fedora who have patched vte, this
        # will trigger a desktop notification and bring attention
        # to the terminal.
        #
        vte_version = os.environ.get("VTE_VERSION")
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
