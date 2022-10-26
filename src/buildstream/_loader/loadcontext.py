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

from .._exceptions import LoadError
from ..exceptions import LoadErrorReason
from ..types import _ProjectInformation


# ProjectLoaders()
#
# An object representing all of the loaders for a given project.
#
class ProjectLoaders:
    def __init__(self, project_name):

        # The project name
        self._name = project_name

        # A list of all loaded loaders for this project
        self._collect = []

    # register_loader()
    #
    # Register a Loader for this project
    #
    # Args:
    #    loader (Loader): The loader to register
    #
    def register_loader(self, loader):
        assert loader.project.name == self._name

        self._collect.append(loader)

    # assert_loaders():
    #
    # Asserts the validity of loaders for this project
    #
    # Raises:
    #    (LoadError): In case there is a CONFLICTING_JUNCTION error
    #
    def assert_loaders(self):
        duplicates = {}
        internal = {}
        primary = []

        for loader in self._collect:
            duplicating, internalizing = self._search_project_relationships(loader)
            if duplicating:
                duplicates[loader] = duplicating
            if internalizing:
                internal[loader] = internalizing

            if not (duplicating or internalizing):
                primary.append(loader)

        if len(primary) > 1:
            self._raise_conflict(duplicates, internal)

        elif primary and duplicates:
            self._raise_conflict(duplicates, internal)

    # loaded_projects()
    #
    # A generator which yeilds all of the instances
    # of this loaded project.
    #
    # Yields:
    #    (_ProjectInformation): A descriptive project information object
    #
    def loaded_projects(self):
        for loader in self._collect:
            duplicating, internalizing = self._search_project_relationships(loader)
            yield _ProjectInformation(
                loader.project, loader.provenance_node, [str(l) for l in duplicating], [str(l) for l in internalizing]
            )

    # _search_project_relationships()
    #
    # Searches this loader's ancestry for projects which mark this
    # loader as internal or duplicate
    #
    # Args:
    #    loader (Loader): The loader to search for duplicate markers of
    #
    # Returns:
    #    (list): A list of Loader objects who's project has marked
    #            this junction as a duplicate
    #    (list): A list of Loader objects who's project has marked
    #            this junction as internal
    #
    def _search_project_relationships(self, loader):
        duplicates = []
        internal = []
        for parent in loader.ancestors():
            if parent.project.junction_is_duplicated(self._name, loader):
                duplicates.append(parent)
            if parent.project.junction_is_internal(loader):
                internal.append(parent)
        return duplicates, internal

    # _raise_conflict()
    #
    # Raises the LoadError indicating there was a conflict, this
    # will list all of the instances in which the project has
    # been loaded as the LoadError detail string
    #
    # Args:
    #    duplicates (dict): A table of duplicating Loaders, indexed
    #                       by duplicated Loader
    #    internals (dict): A table of Loaders which mark a loader as internal,
    #                      indexed by internal Loader
    #
    # Raises:
    #    (LoadError): In case there is a CONFLICTING_JUNCTION error
    #
    def _raise_conflict(self, duplicates, internals):
        explanation = (
            "Internal projects do not cause any conflicts. Conflicts can also be avoided\n"
            + "by marking every instance of the project as a duplicate."
        )
        lines = [self._loader_description(loader, duplicates, internals) for loader in self._collect]
        detail = "{}\n{}".format("\n".join(lines), explanation)

        raise LoadError(
            "Project '{}' was loaded in multiple contexts".format(self._name),
            LoadErrorReason.CONFLICTING_JUNCTION,
            detail=detail,
        )

    # _loader_description()
    #
    # Args:
    #    loader (Loader): The loader to describe
    #    duplicates (dict): A table of duplicating Loaders, indexed
    #                       by duplicated Loader
    #    internals (dict): A table of Loaders which mark a loader as internal,
    #                      indexed by internal Loader
    #
    # Returns:
    #    (str): A string representing how this loader was loaded
    #
    def _loader_description(self, loader, duplicates, internals):

        line = "{}\n".format(loader)

        # Mention projects which have marked this project as a duplicate
        duplicating = duplicates.get(loader)
        if duplicating:
            for dup in duplicating:
                line += "  Duplicated by: {}\n".format(dup)

        # Mention projects which have marked this project as internal
        internalizing = internals.get(loader)
        if internalizing:
            for internal in internalizing:
                line += "  Internal to: {}\n".format(internal)

        return line


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

    # assert_loaders()
    #
    # Asserts that there are no conflicting projects loaded.
    #
    # Raises:
    #    (LoadError): A CONFLICTING_JUNCTION LoadError in the case of a conflict
    #
    def assert_loaders(self):
        for _, loaders in self._loaders.items():
            loaders.assert_loaders()

    # register_loader()
    #
    # Registers a new loader in the load context, possibly
    # raising an error in the case of a conflict.
    #
    # This must be called after a recursive load process has completed,
    # and after the pipeline is resolved (which is to say that all related
    # Plugin derived objects have been instantiated).
    #
    # Args:
    #    loader (Loader): The Loader object to register into context
    #
    def register_loader(self, loader):
        project = loader.project

        try:
            project_loaders = self._loaders[project.name]
        except KeyError:
            project_loaders = ProjectLoaders(project.name)
            self._loaders[project.name] = project_loaders

        project_loaders.register_loader(loader)

    # loaded_projects()
    #
    # A generator which yeilds all of the loaded projects
    #
    # Yields:
    #    (_ProjectInformation): A descriptive project information object
    #
    def loaded_projects(self):
        for _, project_loaders in self._loaders.items():
            yield from project_loaders.loaded_projects()
