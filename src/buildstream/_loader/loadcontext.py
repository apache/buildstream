#
#  Copyright (C) 2020 Codethink Limited
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


# LoaderContext()
#
# An object to keep track of overall context during the load process.
#
# Args:
#    context (Context): The invocation context
#
class LoadContext:
    def __init__(self, context):

        # Keep track of global context required throughout the recursive load
        self.context = context
        self.rewritable = False
        self.fetch_subprojects = None
        self.task = None

    # set_rewritable()
    #
    # Sets whether the projects are to be loaded in a rewritable fashion,
    # this is used for tracking and is slightly more expensive in load time.
    #
    # Args:
    #   task (Task): The task to report progress on
    #
    def set_rewritable(self, rewritable):
        self.rewritable = rewritable

    # set_task()
    #
    # Sets the task for progress reporting.
    #
    # Args:
    #   task (Task): The task to report progress on
    #
    def set_task(self, task):
        self.task = task

    # set_fetch_subprojects()
    #
    # Sets the task for progress reporting.
    #
    # Args:
    #   task (callable): The callable for loading subprojects
    #
    def set_fetch_subprojects(self, fetch_subprojects):
        self.fetch_subprojects = fetch_subprojects
