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

from . import _yaml
from .node import _new_synthetic_file
from ._exceptions import LoadError
from .exceptions import LoadErrorReason


# ProjectRefStorage()
#
# Indicates the type of ref storage
class ProjectRefStorage:

    # Source references are stored inline
    #
    INLINE = "inline"

    # Source references are stored in a central project.refs file
    #
    PROJECT_REFS = "project.refs"


# ProjectRefs()
#
# The project.refs file management
#
# Args:
#    directory (str): The project directory
#    base_name (str): The project.refs basename
#
class ProjectRefs:
    def __init__(self, directory, base_name):
        directory = os.path.abspath(directory)
        self._fullpath = os.path.join(directory, base_name)
        self._base_name = base_name
        self._toplevel_node = None
        self._toplevel_save = None

    # load()
    #
    # Load the project.refs file
    #
    # Args:
    #    options (OptionPool): To resolve conditional statements
    #
    def load(self, options):
        try:
            self._toplevel_node = _yaml.load(self._fullpath, shortname=self._base_name, copy_tree=True)
            provenance = self._toplevel_node.get_provenance()
            self._toplevel_save = provenance._toplevel

            # Process any project options immediately
            options.process_node(self._toplevel_node)

            # Run any final assertions on the project.refs, just incase there
            # are list composition directives or anything left unprocessed.
            self._toplevel_node._assert_fully_composited()

        except LoadError as e:
            if e.reason != LoadErrorReason.MISSING_FILE:
                raise

            # Ignore failure if the file doesnt exist, it'll be created and
            # for now just assumed to be empty
            self._toplevel_node = _new_synthetic_file(self._fullpath)
            self._toplevel_save = self._toplevel_node

        self._toplevel_node.validate_keys(["projects"])

        # Ensure we create our toplevel entry point on the fly here
        for node in [self._toplevel_node, self._toplevel_save]:
            if "projects" not in node:
                node["projects"] = {}

    # lookup_ref()
    #
    # Fetch the ref node for a given Source. If the ref node does not
    # exist and `write` is specified, it will be automatically created.
    #
    # Args:
    #    project (str): The project to lookup
    #    element (str): The element name to lookup
    #    source_index (int): The index of the Source in the specified element
    #    write (bool): Whether we want to read the node or write to it
    #
    # Returns:
    #    (node): The YAML dictionary where the ref is stored
    #
    def lookup_ref(self, project, element, source_index, *, write=False):

        node = self._lookup(self._toplevel_node, project, element, source_index)

        if write:

            # If we couldnt find the orignal, create a new one.
            #
            if node is None:
                node = self._lookup(self._toplevel_save, project, element, source_index, ensure=True)

        return node

    # _lookup()
    #
    # Looks up a ref node in the project.refs file, creates one if ensure is True.
    #
    def _lookup(self, toplevel, project, element, source_index, *, ensure=False):
        projects = toplevel.get_mapping("projects")

        # Fetch the project
        try:
            project_node = projects.get_mapping(project)
        except LoadError:
            if not ensure:
                return None
            projects[project] = {}
            project_node = projects.get_mapping(project)

        # Fetch the element
        try:
            element_list = project_node.get_sequence(element)
        except LoadError:
            if not ensure:
                return None
            project_node[element] = []
            element_list = project_node.get_sequence(element)

        # Fetch the source index
        try:
            node = element_list.mapping_at(source_index)
        except IndexError:
            if not ensure:
                return None

            element_list.append({})
            node = element_list.mapping_at(source_index)

        return node
