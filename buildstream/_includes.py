import os
from collections.abc import Mapping
from . import _yaml
from ._exceptions import LoadError, LoadErrorReason


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
    #    included (set): Fail for recursion if trying to load any files in this set
    #    current_loader (Loader): Use alternative loader (for junction files)
    #    only_local (bool): Whether to ignore junction files
    def process(self, node, *,
                included=set(),
                current_loader=None,
                only_local=False):
        if current_loader is None:
            current_loader = self._loader

        if isinstance(node.get('(@)'), str):
            includes = [_yaml.node_get(node, str, '(@)')]
        else:
            includes = _yaml.node_get(node, list, '(@)', default_value=None)

        include_provenance = None
        if '(@)' in node:
            include_provenance = _yaml.node_get_provenance(node, key='(@)')
            del node['(@)']

        if includes:
            for include in reversed(includes):
                if only_local and ':' in include:
                    continue
                try:
                    include_node, file_path, sub_loader = self._include_file(include,
                                                                             current_loader)
                except LoadError as e:
                    if e.reason == LoadErrorReason.MISSING_FILE:
                        message = "{}: Include block references a file that could not be found: '{}'.".format(
                            include_provenance, include)
                        raise LoadError(LoadErrorReason.MISSING_FILE, message) from e
                    elif e.reason == LoadErrorReason.LOADING_DIRECTORY:
                        message = "{}: Include block references a directory instead of a file: '{}'.".format(
                            include_provenance, include)
                        raise LoadError(LoadErrorReason.LOADING_DIRECTORY, message) from e
                    else:
                        raise

                if file_path in included:
                    raise LoadError(LoadErrorReason.RECURSIVE_INCLUDE,
                                    "{}: trying to recursively include {}". format(include_provenance,
                                                                                   file_path))
                # Because the included node will be modified, we need
                # to copy it so that we do not modify the toplevel
                # node of the provenance.
                include_node = _yaml.node_copy(include_node)

                try:
                    included.add(file_path)
                    self.process(include_node, included=included,
                                 current_loader=sub_loader,
                                 only_local=only_local)
                finally:
                    included.remove(file_path)

                _yaml.composite_and_move(node, include_node)

        for _, value in _yaml.node_items(node):
            self._process_value(value,
                                included=included,
                                current_loader=current_loader,
                                only_local=only_local)

    # _include_file()
    #
    # Load include YAML file from with a loader.
    #
    # Args:
    #    include (str): file path relative to loader's project directory.
    #                   Can be prefixed with junctio name.
    #    loader (Loader): Loader for the current project.
    def _include_file(self, include, loader):
        shortname = include
        if ':' in include:
            junction, include = include.split(':', 1)
            junction_loader = loader._get_loader(junction, fetch_subprojects=True)
            current_loader = junction_loader
        else:
            current_loader = loader
        project = current_loader.project
        directory = project.directory
        file_path = os.path.join(directory, include)
        key = (current_loader, file_path)
        if key not in self._loaded:
            self._loaded[key] = _yaml.load(file_path,
                                           shortname=shortname,
                                           project=project,
                                           copy_tree=self._copy_tree)
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
    def _process_value(self, value, *,
                       included=set(),
                       current_loader=None,
                       only_local=False):
        if isinstance(value, Mapping):
            self.process(value,
                         included=included,
                         current_loader=current_loader,
                         only_local=only_local)
        elif isinstance(value, list):
            for v in value:
                self._process_value(v,
                                    included=included,
                                    current_loader=current_loader,
                                    only_local=only_local)
