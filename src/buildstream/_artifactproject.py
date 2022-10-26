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
