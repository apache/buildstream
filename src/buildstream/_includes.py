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
import os
from . import _yaml
from .node import MappingNode, ScalarNode, SequenceNode
from ._variables import Variables
from ._exceptions import LoadError
from .exceptions import LoadErrorReason


# Includes()
#
# This takes care of processing include directives "(@)".
#
# Args:
#    loader (Loader): The Loader object
#    copy_tree (bool): Whether to make a copy, of tree in
#                      provenance. Should be true if intended to be
#                      serialized.
class Includes:
    def __init__(self, loader, *, copy_tree=False):
        self._loader = loader
        self._loaded = {}
        self._copy_tree = copy_tree

    # process()
    #
    # Process recursively include directives in a YAML node.
    #
    # Args:
    #    node (dict): A YAML node
    #    only_local (bool): Whether to ignore junction files
    #    process_project_options (bool): Whether to process options from current project
    def process(self, node, *, only_local=False, process_project_options=True):
        self._process(node, only_local=only_local, process_project_options=process_project_options)

    # _process()
    #
    # Process recursively include directives in a YAML node. This
    # method is a recursively called on loaded nodes from files.
    #
    # Args:
    #    node (dict): A YAML node
    #    included (set): Fail for recursion if trying to load any files in this set
    #    current_loader (Loader): Use alternative loader (for junction files)
    #    only_local (bool): Whether to ignore junction files
    #    process_project_options (bool): Whether to process options from current project
    def _process(self, node, *, included=None, current_loader=None, only_local=False, process_project_options=True):
        if current_loader is None:
            current_loader = self._loader

        if process_project_options:
            current_loader.project.options.process_node(node)

        self._process_node(
            node,
            included=included,
            only_local=only_local,
            current_loader=current_loader,
            process_project_options=process_project_options,
        )

    # _process_node()
    #
    # Process recursively include directives in a YAML node. This
    # method is recursively called on all nodes.
    #
    # Args:
    #    node (dict): A YAML node
    #    included (set): Fail for recursion if trying to load any files in this set
    #    current_loader (Loader): Use alternative loader (for junction files)
    #    only_local (bool): Whether to ignore junction files
    #    process_project_options (bool): Whether to process options from current project
    def _process_node(
        self, node, *, included=None, current_loader=None, only_local=False, process_project_options=True
    ):
        if included is None:
            included = set()

        includes_node = node.get_node("(@)", allowed_types=[ScalarNode, SequenceNode], allow_none=True)

        if includes_node:
            if type(includes_node) is ScalarNode:  # pylint: disable=unidiomatic-typecheck
                includes = [includes_node]
            else:
                includes = includes_node

            del node["(@)"]

            for include in reversed(includes):
                if only_local and ":" in include.as_str():
                    continue

                include_node, file_path, sub_loader = self._include_file(include, current_loader)
                if file_path in included:
                    include_provenance = includes_node.get_provenance()
                    raise LoadError(
                        "{}: trying to recursively include {}".format(include_provenance, file_path),
                        LoadErrorReason.RECURSIVE_INCLUDE,
                    )

                # Because the included node will be modified, we need
                # to copy it so that we do not modify the toplevel
                # node of the provenance.
                include_node = include_node.clone()

                try:
                    included.add(file_path)
                    self._process(
                        include_node,
                        included=included,
                        current_loader=sub_loader,
                        only_local=only_local,
                        process_project_options=process_project_options or current_loader != sub_loader,
                    )
                finally:
                    included.remove(file_path)

                include_node._composite_under(node)

        for value in node.values():
            self._process_value(
                value,
                included=included,
                current_loader=current_loader,
                only_local=only_local,
                process_project_options=process_project_options,
            )

    # _include_file()
    #
    # Load include YAML file from with a loader.
    #
    # Args:
    #    include (ScalarNode): file path relative to loader's project directory.
    #                          Can be prefixed with junctio name.
    #    loader (Loader): Loader for the current project.
    def _include_file(self, include, loader):
        include_str = include.as_str()
        shortname = include_str
        if ":" in include_str:
            junction, include_str = include_str.rsplit(":", 1)
            current_loader = loader.get_loader(junction, include)
            current_loader.project.ensure_fully_loaded()
        else:
            current_loader = loader
        project = current_loader.project
        directory = project.directory
        file_path = os.path.join(directory, include_str)
        key = (current_loader, file_path)
        if key not in self._loaded:
            try:
                self._loaded[key] = _yaml.load(
                    file_path, shortname=shortname, project=project, copy_tree=self._copy_tree
                )
            except LoadError as e:
                raise LoadError("{}: {}".format(include.get_provenance(), e), e.reason, detail=e.detail) from e

            # If the include is from a subproject, we need to expand variables
            # in the context of the subproject's variables, the subproject is
            # guaranteed at this stage to be fully loaded.
            #
            if current_loader != loader:
                variables_node = current_loader.project.base_variables.clone()
                variables = Variables(variables_node)
                variables.expand(self._loaded[key])

        return self._loaded[key], file_path, current_loader

    # _process_value()
    #
    # Select processing for value that could be a list or a dictionary.
    #
    # Args:
    #    value: Value to process. Can be a list or a dictionary.
    #    included (set): Fail for recursion if trying to load any files in this set
    #    current_loader (Loader): Use alternative loader (for junction files)
    #    only_local (bool): Whether to ignore junction files
    #    process_project_options (bool): Whether to process options from current project
    def _process_value(
        self, value, *, included=None, current_loader=None, only_local=False, process_project_options=True
    ):
        value_type = type(value)

        if value_type is MappingNode:
            self._process_node(
                value,
                included=included,
                current_loader=current_loader,
                only_local=only_local,
                process_project_options=process_project_options,
            )
        elif value_type is SequenceNode:
            for v in value:
                self._process_value(
                    v,
                    included=included,
                    current_loader=current_loader,
                    only_local=only_local,
                    process_project_options=process_project_options,
                )
