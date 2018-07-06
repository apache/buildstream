import os
import copy
from collections import Mapping
from . import _yaml
from ._exceptions import LoadError, LoadErrorReason


class Includes:

    def __init__(self, loader):
        self._loader = loader
        self._loaded = {}

    def process(self, node, *,
                included=set(),
                current_loader=None,
                only_local=False):
        if current_loader is None:
            current_loader = self._loader

        includes = _yaml.node_get(node, list, '(@)', default_value=None)
        if '(@)' in node:
            del node['(@)']

        if includes:
            for include in includes:
                if only_local and ':' in include:
                    continue
                include_node, file_path, sub_loader = self._include_file(include,
                                                                         current_loader)
                if file_path in included:
                    provenance = _yaml.node_get_provenance(node)
                    raise LoadError(LoadErrorReason.RECURSIVE_INCLUDE,
                                    "{}: trying to recursively include {}". format(provenance,
                                                                                   file_path))
                try:
                    included.add(file_path)
                    self.process(include_node, included=included,
                                 current_loader=sub_loader,
                                 only_local=only_local)
                finally:
                    included.remove(file_path)

                old_node = copy.copy(node)
                while True:
                    try:
                        node.popitem()
                    except KeyError:
                        break
                _yaml.composite(node, include_node)
                _yaml.composite(node, old_node)
                
        for _, value in _yaml.node_items(node):
            self._process_value(value, current_loader=current_loader,
                                only_local=only_local)

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
        if file_path not in self._loaded:
            self._loaded[key] = _yaml.load(os.path.join(directory, include),
                                           shortname=shortname,
                                           project=project)
        return self._loaded[key], file_path, current_loader

    def _process_value(self, value, *,
                       current_loader=None,
                       only_local=False):
        if isinstance(value, Mapping):
            self.process(value, current_loader=current_loader, only_local=only_local)
        elif isinstance(value, list):
            self._process_list(value, current_loader=current_loader, only_local=only_local)

    def _process_list(self, values, *,
                      current_loader=None,
                      only_local=False):
        for value in values:
            self._process_value(value, current_loader=current_loader, only_local=only_local)
