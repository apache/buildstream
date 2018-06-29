import os
from collections import Mapping
from . import _yaml
from ._exceptions import LoadError, LoadErrorReason


class Includes:

    def __init__(self, loader):
        self._loader = loader
        self._loaded = {}

    def ignore_includes(self, node):
        if isinstance(node, Mapping):
            if '(@)' in node:
                del node['(@)']
            for _, value in _yaml.node_items(node):
                self.ignore_includes(value)
        elif isinstance(node, list):
            for value in node:
                self.ignore_includes(value)

    def process(self, node, *, included=set()):
        includes = _yaml.node_get(node, list, '(@)', default_value=None)
        if '(@)' in node:
            del node['(@)']

        if includes:
            for include in includes:
                include_node, file_path = self._include_file(include)
                if file_path in included:
                    provenance = _yaml.node_get_provenance(node)
                    raise LoadError(LoadErrorReason.RECURSIVE_INCLUDE,
                                    "{}: trying to recursively include {}". format(provenance,
                                                                                   file_path))
                try:
                    included.add(file_path)
                    self.process(include_node, included=included)
                finally:
                    included.remove(file_path)
                _yaml.composite(node, include_node)

        for _, value in _yaml.node_items(node):
            self._process_value(value)

    def _include_file(self, include):
        shortname = include
        if ':' in include:
            junction, include = include.split(':', 1)
            junction_loader = self._loader._get_loader(junction, fetch_subprojects=True)
            project = junction_loader.project
        else:
            project = self._loader.project
        directory = project.directory
        file_path = os.path.join(directory, include)
        if file_path not in self._loaded:
            self._loaded[file_path] = _yaml.load(os.path.join(directory, include),
                                                 shortname=shortname,
                                                 project=project)
        return self._loaded[file_path], file_path

    def _process_value(self, value):
        if isinstance(value, Mapping):
            self.process(value)
        elif isinstance(value, list):
            self._process_list(value)

    def _process_list(self, values):
        for value in values:
            self._process_value(value)
