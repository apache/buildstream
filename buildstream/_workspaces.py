#!/usr/bin/env python3
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

from ._exceptions import LoadError, LoadErrorReason


BST_WORKSPACE_FORMAT_VERSION = 2


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
#    path (str): The path that should host this workspace
#    project (Project): The project this workspace is part of
#    last_successful (str): The key of the last successful build of this workspace
#    running_files (dict): A dict mapping dependency elements to files
#                          changed between failed builds. Should be
#                          made obsolete with failed build artifacts.
#
class Workspace():
    def __init__(self, path, project, last_successful=None, running_files=None):
        self.last_successful = last_successful
        self.path = path
        self.running_files = running_files if running_files is not None else {}

        self._element = None
        self._project = project
        self.__key = None

    @classmethod
    def from_yaml_node(cls, node, project):
        path = _yaml.node_get(node, str, 'path')
        last_successful = _yaml.node_get(node, str, 'last_successful', default_value=None)
        running_files = _yaml.node_get(node, dict, 'running_files', default_value=None)

        return cls(path, project, last_successful, running_files)

    # _to_dict()
    #
    # Convert this object to a dict for storage purposes
    #
    # Returns:
    #     (dict) A dict representation of the workspace
    #
    def _to_dict(self):
        to_return = ['path', 'last_successful', 'running_files']

        return {key: val for key, val in self.__dict__.items()
                if key in to_return and val is not None}

    # open()
    #
    # "Open" this workspace, calling the init_workspace method of all
    # its sources.
    #
    def open(self):
        for source in self._element.sources():
            source._init_workspace(self.path)

    # init()
    #
    # Initialize the elements and sources associated to this
    # workspace. Must be called before this object is used.
    #
    def init(self, element):
        self._element = element

    # invalidate_key()
    #
    # Invalidate the workspace key, forcing a recalculation next time
    # it is accessed.
    #
    def invalidate_key(self):
        self.__key = None

    # stage()
    #
    # Stage the workspace to the given directory.
    #
    # Args:
    #    directory (str) - The directory into which to stage this workspace
    #
    def stage(self, directory):
        fullpath = os.path.join(self._project.directory, self.path)
        if os.path.isdir(fullpath):
            utils.copy_files(fullpath, directory)
        else:
            destfile = os.path.join(directory, os.path.basename(self.path))
            utils.safe_copy(fullpath, destfile)

    # add_running_files()
    #
    # Append a list of files to the running_files for the given
    # dependency. Duplicate files will be ignored.
    #
    # Args:
    #     dep (Element) - The dependency whose files to append to
    #     files (str) - A list of files to append
    #
    def add_running_files(self, dep, files):
        if dep.name in self.running_files:
            # ruamel.py cannot serialize sets in python3.4
            to_add = set(files) - set(self.running_files[dep.name])
            self.running_files[dep.name].extend(to_add)
        else:
            self.running_files[dep.name] = list(files)

    # clear_running_files()
    #
    # Clear all running files associated with this workspace.
    #
    def clear_running_files(self):
        self.running_files = {}

    # get_key()
    #
    # Get a unique key for this workspace.
    #
    # Args:
    #    recalculate (bool) - Whether to recalculate the key
    #
    # Returns:
    #    (str) A unique key for this workspace
    #
    def get_key(self, recalculate=False):
        def unique_key(filename):
            if os.path.isdir(filename):
                return "0"
            elif os.path.islink(filename):
                return "1"

            try:
                return utils.sha256sum(filename)
            except FileNotFoundError as e:
                raise LoadError(LoadErrorReason.MISSING_FILE,
                                "Failed loading workspace. Did you remove the "
                                "workspace directory? {}".format(e))

        if recalculate or self.__key is None:
            fullpath = os.path.join(self._project.directory, self.path)

            # Get a list of tuples of the the project relative paths and fullpaths
            if os.path.isdir(fullpath):
                filelist = utils.list_relative_paths(fullpath)
                filelist = [(relpath, os.path.join(fullpath, relpath)) for relpath in filelist]
            else:
                filelist = [(self.path, fullpath)]

            self.__key = [(relpath, unique_key(fullpath)) for relpath, fullpath in filelist]

        return self.__key

    # get_absolute_path():
    #
    # Returns: The absolute path of the element's workspace.
    #
    def get_absolute_path(self):
        return os.path.join(self._project.directory, self.path)


# Workspaces()
#
# A class to manage Workspaces for multiple elements.
#
# Args:
#    project (Project): The project the workspaces should be associated to
#
class Workspaces():
    def __init__(self, project):
        self._project = project
        workspace_config = self._load_config()
        self._workspaces = self._parse_workspace_config(workspace_config)

    # _list_workspaces()
    #
    # Generator function to enumerate workspaces.
    #
    # Yields:
    #    A tuple in the following format: (str, Workspace), where the
    #    first element is the name of the workspaced element.
    def list(self):
        for element, _ in _yaml.node_items(self._workspaces):
            yield (element, self._workspaces[element])

    # create_workspace()
    #
    # Create a workspace in the given path for the given element.
    #
    # Args:
    #    element (Element) - The element for which to create a workspace
    #    path (str) - The path in which the workspace should be kept
    #
    def create_workspace(self, element, path):
        self._workspaces[element.name] = Workspace(path, self._project)
        self._workspaces[element.name].init(element)

        return self._workspaces[element.name]

    # _get_workspace()
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
        del self._workspaces[element_name]

    # save_config()
    #
    # Dump the current workspace element to the project configuration
    # file. This makes any changes performed with delete_workspace or
    # create_workspace permanent
    #
    def save_config(self):
        config = {
            'format-version': BST_WORKSPACE_FORMAT_VERSION,
            'workspaces': {
                element: workspace._to_dict()
                for element, workspace in _yaml.node_items(self._workspaces)
            }
        }
        os.makedirs(os.path.join(self._project.directory, ".bst"), exist_ok=True)
        _yaml.dump(_yaml.node_sanitize(config),
                   os.path.join(self._project.directory, ".bst", "workspaces.yml"))

    # _load_config()
    #
    # Load the workspace configuration and return a node containing
    # all open workspaces for the project
    #
    # Returns:
    #
    #    A node containing a dict that assigns elements to their
    #    workspaces. For example:
    #
    #        alpha.bst: /home/me/alpha
    #        bravo.bst: /home/me/bravo
    #
    def _load_config(self):
        workspace_file = os.path.join(self._project.directory, ".bst", "workspaces.yml")
        try:
            node = _yaml.load(workspace_file)
        except LoadError as e:
            if e.reason == LoadErrorReason.MISSING_FILE:
                # Return an empty dict if there was no workspace file
                return {}

            raise

        return node

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
        version = _yaml.node_get(workspaces, int, "format-version", default_value=0)

        if version == 0:
            # Pre-versioning format can be of two forms
            for element, config in _yaml.node_items(workspaces):
                if isinstance(config, str):
                    pass

                elif isinstance(config, dict):
                    sources = list(_yaml.node_items(config))
                    if len(sources) > 1:
                        detail = "There are multiple workspaces open for '{}'.\n" + \
                                 "This is not supported anymore.\n" + \
                                 "Please remove this element from '{}'."
                        raise LoadError(LoadErrorReason.INVALID_DATA,
                                        detail.format(element,
                                                      os.path.join(self._project.directory, ".bst", "workspaces.yml")))

                    workspaces[element] = sources[0][1]

                else:
                    raise LoadError(LoadErrorReason.INVALID_DATA,
                                    "Workspace config is in unexpected format.")

            res = {
                element: Workspace(config, self._project)
                for element, config in _yaml.node_items(workspaces)
            }

        elif version == 1 or version == BST_WORKSPACE_FORMAT_VERSION:
            workspaces = _yaml.node_get(workspaces, dict, "workspaces", default_value={})
            res = {element: Workspace.from_yaml_node(node, self._project)
                   for element, node in _yaml.node_items(workspaces)}

        else:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "Workspace configuration format version {} not supported."
                            "Your version of buildstream may be too old. Max supported version: {}"
                            .format(version, BST_WORKSPACE_FORMAT_VERSION))

        return res
