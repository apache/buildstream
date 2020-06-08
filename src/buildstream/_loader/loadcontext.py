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

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason


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

        # A table of all Loaders, indexed by project name
        self._loaders = {}

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

    # register_loader()
    #
    # Registers a new loader in the load context, possibly
    # raising an error in the case of a conflict
    #
    # Args:
    #    loader (Loader): The Loader object to register into context
    #
    # Raises:
    #    (LoadError): A CONFLICTING_JUNCTION LoadError in the case of a conflict
    #
    def register_loader(self, loader):
        project = loader.project
        existing_loader = self._loaders.get(project.name, None)

        if existing_loader:

            assert project.junction is not None

            if existing_loader.project.junction:
                # The existing provenance can be None even if there is a junction, this
                # can happen when specifying a full element path on the command line.
                #
                provenance_str = ""
                if existing_loader.provenance:
                    provenance_str = ": {}".format(existing_loader.provenance)

                detail = "Project '{}' was already loaded by junction '{}'{}".format(
                    project.name, existing_loader.project.junction._get_full_name(), provenance_str
                )
            else:
                detail = "Project '{}' is also the toplevel project".format(project.name)

            raise LoadError(
                "{}: Error loading project '{}' from junction: {}".format(
                    loader.provenance, project.name, project.junction._get_full_name()
                ),
                LoadErrorReason.CONFLICTING_JUNCTION,
                detail=detail,
            )
        self._loaders[project.name] = loader
