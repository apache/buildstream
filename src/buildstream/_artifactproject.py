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
#
from contextlib import suppress
from typing import TYPE_CHECKING

from ._project import Project
from ._context import Context
from ._loader import Loader

if TYPE_CHECKING:
    from typing import Dict


# ArtifactProject()
#
# A project instance to be used as the project for an ArtifactElement.
#
# This is basically a simplified Project implementation which ensures that
# we do not accidentally infer any data from a possibly present local project
# when processing an ArtifactElement.
#
# Args:
#    project_name: The name of this project
#
class ArtifactProject(Project):

    __loaded_artifact_projects = {}  # type: Dict[str, ArtifactProject]

    def __init__(self, project_name: str, context: Context):

        #
        # Chain up to the Project constructor, and allow it to initialize
        # without loading anything
        #
        super().__init__(None, context, search_for_project=False)

        # Fill in some necessities
        #
        self.name = project_name
        self.element_path = ""  # This needs to be set to avoid Loader crashes
        self.loader = Loader(self)

    # get_artifact_project():
    #
    # Gets a reference to an ArtifactProject for the given
    # project name, possibly instantiating one if needed.
    #
    # Args:
    #    project_name: The project name
    #    context: The Context
    #
    # Returns:
    #    An ArtifactProject with the given project_name
    #
    @classmethod
    def get_artifact_project(cls, project_name: str, context: Context) -> "ArtifactProject":
        with suppress(KeyError):
            return cls.__loaded_artifact_projects[project_name]

        project = cls(project_name, context)
        cls.__loaded_artifact_projects[project_name] = project
        return project

    # clear_project_cache():
    #
    # Clears the cache of loaded projects, this can be called directly
    # after completing a full load.
    #
    @classmethod
    def clear_project_cache(cls):
        cls.__loaded_artifact_projects = {}
