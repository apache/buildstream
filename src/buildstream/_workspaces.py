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
#        Tristan Maat <tristan.maat@codethink.co.uk>

import os
from . import utils
from . import _yaml

from .node import MappingNode, ScalarNode
from ._exceptions import LoadError, LoadErrorReason


BST_WORKSPACE_FORMAT_VERSION = 3
BST_WORKSPACE_PROJECT_FORMAT_VERSION = 1
WORKSPACE_PROJECT_FILE = ".bstproject.yaml"


# WorkspaceProject()
#
# An object to contain various helper functions and data required for
# referring from a workspace back to buildstream.
#
# Args:
#    directory (str): The directory that the workspace exists in.
#
class WorkspaceProject:
    def __init__(self, directory):
        self._projects = []
        self._directory = directory

    # get_default_project_path()
    #
    # Retrieves the default path to a project.
    #
    # Returns:
    #    (str): The path to a project
    #
    def get_default_project_path(self):
        return self._projects[0]["project-path"]

    # get_default_element()
    #
    # Retrieves the name of the element that owns this workspace.
    #
    # Returns:
    #    (str): The name of an element
    #
    def get_default_element(self):
        return self._projects[0]["element-name"]

    # to_dict()
    #
    # Turn the members data into a dict for serialization purposes
    #
    # Returns:
    #    (dict): A dict representation of the WorkspaceProject
    #
    def to_dict(self):
        ret = {
            "projects": self._projects,
            "format-version": BST_WORKSPACE_PROJECT_FORMAT_VERSION,
        }
        return ret

    # from_dict()
    #
    # Loads a new WorkspaceProject from a simple dictionary
    #
    # Args:
    #    directory (str): The directory that the workspace exists in
    #    dictionary (dict): The dict to generate a WorkspaceProject from
    #
    # Returns:
    #   (WorkspaceProject): A newly instantiated WorkspaceProject
    #
    @classmethod
    def from_dict(cls, directory, dictionary):
        # Only know how to handle one format-version at the moment.
        format_version = int(dictionary["format-version"])
        assert format_version == BST_WORKSPACE_PROJECT_FORMAT_VERSION, "Format version {} not found in {}".format(
            BST_WORKSPACE_PROJECT_FORMAT_VERSION, dictionary
        )

        workspace_project = cls(directory)
        for item in dictionary["projects"]:
            workspace_project.add_project(item["project-path"], item["element-name"])

        return workspace_project

    # load()
    #
    # Loads the WorkspaceProject for a given directory.
    #
    # Args:
    #    directory (str): The directory
    # Returns:
    #    (WorkspaceProject): The created WorkspaceProject, if in a workspace, or
    #    (NoneType): None, if the directory is not inside a workspace.
    #
    @classmethod
    def load(cls, directory):
        workspace_file = os.path.join(directory, WORKSPACE_PROJECT_FILE)
        if os.path.exists(workspace_file):
            data_dict = _yaml.roundtrip_load(workspace_file)

            return cls.from_dict(directory, data_dict)
        else:
            return None

    # write()
    #
    # Writes the WorkspaceProject to disk
    #
    def write(self):
        os.makedirs(self._directory, exist_ok=True)
        _yaml.roundtrip_dump(self.to_dict(), self.get_filename())

    # get_filename()
    #
    # Returns the full path to the workspace local project file
    #
    def get_filename(self):
        return os.path.join(self._directory, WORKSPACE_PROJECT_FILE)

    # add_project()
    #
    # Adds an entry containing the project's path and element's name.
    #
    # Args:
    #    project_path (str): The path to the project that opened the workspace.
    #    element_name (str): The name of the element that the workspace belongs to.
    #
    def add_project(self, project_path, element_name):
        assert project_path and element_name
        self._projects.append({"project-path": project_path, "element-name": element_name})


# WorkspaceProjectCache()
#
# A class to manage workspace project data for multiple workspaces.
#
class WorkspaceProjectCache:
    def __init__(self):
        self._projects = {}  # Mapping of a workspace directory to its WorkspaceProject

    # get()
    #
    # Returns a WorkspaceProject for a given directory, retrieving from the cache if
    # present.
    #
    # Args:
    #    directory (str): The directory to search for a WorkspaceProject.
    #
    # Returns:
    #    (WorkspaceProject): The WorkspaceProject that was found for that directory.
    #    or      (NoneType): None, if no WorkspaceProject can be found.
    #
    def get(self, directory):
        try:
            workspace_project = self._projects[directory]
        except KeyError:
            workspace_project = WorkspaceProject.load(directory)
            if workspace_project:
                self._projects[directory] = workspace_project

        return workspace_project

    # add()
    #
    # Adds the project path and element name to the WorkspaceProject that exists
    # for that directory
    #
    # Args:
    #    directory (str): The directory to search for a WorkspaceProject.
    #    project_path (str): The path to the project that refers to this workspace
    #    element_name (str): The element in the project that was refers to this workspace
    #
    # Returns:
    #    (WorkspaceProject): The WorkspaceProject that was found for that directory.
    #
    def add(self, directory, project_path, element_name):
        workspace_project = self.get(directory)
        if not workspace_project:
            workspace_project = WorkspaceProject(directory)
            self._projects[directory] = workspace_project

        workspace_project.add_project(project_path, element_name)
        return workspace_project

    # remove()
    #
    # Removes the project path and element name from the WorkspaceProject that exists
    # for that directory.
    #
    # NOTE: This currently just deletes the file, but with support for multiple
    # projects opening the same workspace, this will involve decreasing the count
    # and deleting the file if there are no more projects.
    #
    # Args:
    #    directory (str): The directory to search for a WorkspaceProject.
    #
    def remove(self, directory):
        workspace_project = self.get(directory)
        if not workspace_project:
            raise LoadError(
                "Failed to find a {} file to remove".format(WORKSPACE_PROJECT_FILE), LoadErrorReason.MISSING_FILE
            )
        path = workspace_project.get_filename()
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


# Workspace()
#
# An object to contain various helper functions and data required for
# workspaces.
#
# last_successful, path and running_files are intended to be public
# properties, but may be best accessed using this classes' helper
# methods.
#
# Args:
#    toplevel_project (Project): Top project. Will be used for resolving relative workspace paths.
#    path (str): The path that should host this workspace
#    last_successful (str): The key of the last successful build of this workspace
#    running_files (dict): A dict mapping dependency elements to files
#                          changed between failed builds. Should be
#                          made obsolete with failed build artifacts.
#
class Workspace:
    def __init__(self, toplevel_project, *, last_successful=None, path=None, prepared=False, running_files=None):
        self.prepared = prepared
        self.last_successful = last_successful
        self._path = path
        self.running_files = running_files if running_files is not None else {}

        self._toplevel_project = toplevel_project
        self._key = None

    # to_dict()
    #
    # Convert a list of members which get serialized to a dict for serialization purposes
    #
    # Returns:
    #     (dict) A dict representation of the workspace
    #
    def to_dict(self):
        ret = {"prepared": self.prepared, "path": self._path, "running_files": self.running_files}
        if self.last_successful is not None:
            ret["last_successful"] = self.last_successful
        return ret

    # from_dict():
    #
    # Loads a new workspace from a simple dictionary, the dictionary
    # is expected to be generated from Workspace.to_dict(), or manually
    # when loading from a YAML file.
    #
    # Args:
    #    toplevel_project (Project): Top project. Will be used for resolving relative workspace paths.
    #    dictionary: A simple dictionary object
    #
    # Returns:
    #    (Workspace): A newly instantiated Workspace
    #
    @classmethod
    def from_dict(cls, toplevel_project, dictionary):

        # Just pass the dictionary as kwargs
        return cls(toplevel_project, **dictionary)

    # differs()
    #
    # Checks if two workspaces are different in any way.
    #
    # Args:
    #    other (Workspace): Another workspace instance
    #
    # Returns:
    #    True if the workspace differs from 'other', otherwise False
    #
    def differs(self, other):
        return self.to_dict() != other.to_dict()

    # stage()
    #
    # Stage the workspace to the given directory.
    #
    # Args:
    #    directory (str) - The directory into which to stage this workspace
    #
    def stage(self, directory):
        fullpath = self.get_absolute_path()
        if os.path.isdir(fullpath):
            utils.copy_files(fullpath, directory)
        else:
            destfile = os.path.join(directory, os.path.basename(self.get_absolute_path()))
            utils.safe_copy(fullpath, destfile)

    # add_running_files()
    #
    # Append a list of files to the running_files for the given
    # dependency. Duplicate files will be ignored.
    #
    # Args:
    #     dep_name (str) - The dependency name whose files to append to
    #     files (str) - A list of files to append
    #
    def add_running_files(self, dep_name, files):
        if dep_name in self.running_files:
            # ruamel.py cannot serialize sets in python3.4
            to_add = set(files) - set(self.running_files[dep_name])
            self.running_files[dep_name].extend(to_add)
        else:
            self.running_files[dep_name] = list(files)

    # clear_running_files()
    #
    # Clear all running files associated with this workspace.
    #
    def clear_running_files(self):
        self.running_files = {}

    # get_absolute_path():
    #
    # Returns: The absolute path of the element's workspace.
    #
    def get_absolute_path(self):
        return os.path.join(self._toplevel_project.directory, self._path)


# Workspaces()
#
# A class to manage Workspaces for multiple elements.
#
# Args:
#    toplevel_project (Project): Top project used to resolve paths.
#    workspace_project_cache (WorkspaceProjectCache): The cache of WorkspaceProjects
#
class Workspaces:
    def __init__(self, toplevel_project, workspace_project_cache):
        self._toplevel_project = toplevel_project
        self._bst_directory = os.path.join(toplevel_project.directory, ".bst")
        self._workspaces = self._load_config()
        self._workspace_project_cache = workspace_project_cache

    # list()
    #
    # Generator function to enumerate workspaces.
    #
    # Yields:
    #    A tuple in the following format: (str, Workspace), where the
    #    first element is the name of the workspaced element.
    def list(self):
        for element in self._workspaces.keys():
            yield (element, self._workspaces[element])

    # create_workspace()
    #
    # Create a workspace in the given path for the given element, and potentially
    # checks-out the target into it.
    #
    # Args:
    #    target (Element) - The element to create a workspace for
    #    path (str) - The path in which the workspace should be kept
    #    checkout (bool): Whether to check-out the element's sources into the directory
    #
    def create_workspace(self, target, path, *, checkout):
        element_name = target._get_full_name()
        project_dir = self._toplevel_project.directory
        if path.startswith(project_dir):
            workspace_path = os.path.relpath(path, project_dir)
        else:
            workspace_path = path

        self._workspaces[element_name] = Workspace(self._toplevel_project, path=workspace_path)

        if checkout:
            with target.timed_activity("Staging sources to {}".format(path)):
                target._open_workspace()

        workspace_project = self._workspace_project_cache.add(path, project_dir, element_name)
        project_file_path = workspace_project.get_filename()

        if os.path.exists(project_file_path):
            target.warn("{} was staged from this element's sources".format(WORKSPACE_PROJECT_FILE))
        workspace_project.write()

        self.save_config()

    # get_workspace()
    #
    # Get the path of the workspace source associated with the given
    # element's source at the given index
    #
    # Args:
    #    element_name (str) - The element name whose workspace to return
    #
    # Returns:
    #    (None|Workspace)
    #
    def get_workspace(self, element_name):
        if element_name not in self._workspaces:
            return None
        return self._workspaces[element_name]

    # update_workspace()
    #
    # Update the datamodel with a new Workspace instance
    #
    # Args:
    #    element_name (str): The name of the element to update a workspace for
    #    workspace_dict (Workspace): A serialized workspace dictionary
    #
    # Returns:
    #    (bool): Whether the workspace has changed as a result
    #
    def update_workspace(self, element_name, workspace_dict):
        assert element_name in self._workspaces

        workspace = Workspace.from_dict(self._toplevel_project, workspace_dict)
        if self._workspaces[element_name].differs(workspace):
            self._workspaces[element_name] = workspace
            return True

        return False

    # delete_workspace()
    #
    # Remove the workspace from the workspace element. Note that this
    # does *not* remove the workspace from the stored yaml
    # configuration, call save_config() afterwards.
    #
    # Args:
    #    element_name (str) - The element name whose workspace to delete
    #
    def delete_workspace(self, element_name):
        workspace = self.get_workspace(element_name)
        del self._workspaces[element_name]

        # Remove from the cache if it exists
        try:
            self._workspace_project_cache.remove(workspace.get_absolute_path())
        except LoadError as e:
            # We might be closing a workspace with a deleted directory
            if e.reason == LoadErrorReason.MISSING_FILE:
                pass
            else:
                raise

    # save_config()
    #
    # Dump the current workspace element to the project configuration
    # file. This makes any changes performed with delete_workspace or
    # create_workspace permanent
    #
    def save_config(self):
        assert utils._is_main_process()

        config = {
            "format-version": BST_WORKSPACE_FORMAT_VERSION,
            "workspaces": {element: workspace.to_dict() for element, workspace in self._workspaces.items()},
        }
        os.makedirs(self._bst_directory, exist_ok=True)
        _yaml.roundtrip_dump(config, self._get_filename())

    # _load_config()
    #
    # Loads and parses the workspace configuration
    #
    # Returns:
    #    (dict) The extracted workspaces
    #
    # Raises: LoadError if there was a problem with the workspace config
    #
    def _load_config(self):
        workspace_file = self._get_filename()
        try:
            node = _yaml.load(workspace_file)
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_FILE:
                # Return an empty dict if there was no workspace file
                return {}

            raise

        return self._parse_workspace_config(node)

    # _parse_workspace_config_format()
    #
    # If workspace config is in old-style format, i.e. it is using
    # source-specific workspaces, try to convert it to element-specific
    # workspaces.
    #
    # Args:
    #    workspaces (dict): current workspace config, usually output of _load_workspace_config()
    #
    # Returns:
    #    (dict) The extracted workspaces
    #
    # Raises: LoadError if there was a problem with the workspace config
    #
    def _parse_workspace_config(self, workspaces):
        try:
            version = workspaces.get_int("format-version", default=0)
        except ValueError:
            raise LoadError(
                "Format version is not an integer in workspace configuration", LoadErrorReason.INVALID_DATA
            )

        if version == 0:
            # Pre-versioning format can be of two forms
            for element, config in workspaces.items():
                config_type = type(config)

                if config_type is ScalarNode:
                    pass

                elif config_type is MappingNode:
                    sources = list(config.values())
                    if len(sources) > 1:
                        detail = (
                            "There are multiple workspaces open for '{}'.\n"
                            + "This is not supported anymore.\n"
                            + "Please remove this element from '{}'."
                        )
                        raise LoadError(detail.format(element, self._get_filename()), LoadErrorReason.INVALID_DATA)

                    workspaces[element] = sources[0]

                else:
                    raise LoadError("Workspace config is in unexpected format.", LoadErrorReason.INVALID_DATA)

            res = {
                element: Workspace(self._toplevel_project, path=config.as_str())
                for element, config in workspaces.items()
            }

        elif 1 <= version <= BST_WORKSPACE_FORMAT_VERSION:
            workspaces = workspaces.get_mapping("workspaces", default={})
            res = {element: self._load_workspace(node) for element, node in workspaces.items()}

        else:
            raise LoadError(
                "Workspace configuration format version {} not supported."
                "Your version of buildstream may be too old. Max supported version: {}".format(
                    version, BST_WORKSPACE_FORMAT_VERSION
                ),
                LoadErrorReason.INVALID_DATA,
            )

        return res

    # _load_workspace():
    #
    # Loads a new workspace from a YAML node
    #
    # Args:
    #    node: A YAML dict
    #
    # Returns:
    #    (Workspace): A newly instantiated Workspace
    #
    def _load_workspace(self, node):
        running_files = node.get_mapping("running_files", default=None)
        if running_files:
            running_files = running_files.strip_node_info()

        dictionary = {
            "prepared": node.get_bool("prepared", default=False),
            "path": node.get_str("path"),
            "last_successful": node.get_str("last_successful", default=None),
            "running_files": running_files,
        }
        return Workspace.from_dict(self._toplevel_project, dictionary)

    # _get_filename():
    #
    # Get the workspaces.yml file path.
    #
    # Returns:
    #    (str): The path to workspaces.yml file.
    def _get_filename(self):
        return os.path.join(self._bst_directory, "workspaces.yml")
