import os
from collections import Mapping
from . import _yaml


class Includes:

    def __init__(self, loader, valid_keys=None):
        self._loader = loader
        self._valid_keys = valid_keys
        self._loaded = {}

    def process(self, node):
        while True:
            includes = _yaml.node_get(node, list, '(@)', default_value=None)
            if '(@)' in node:
                del node['(@)']

            if not includes:
                break

            for include in includes:
                include_node = self._include_file(include)
                if self._valid_keys:
                    _yaml.node_validate(include_node, self._valid_keys)

                _yaml.composite(node, include_node)

        for _, value in _yaml.node_items(node):
            self._process_value(value)

    def _include_file(self, include):
        if ':' in include:
            junction, include = include.split(':', 1)
            junction_loader = self._loader._get_loader(junction, fetch_subprojects=True)
            directory = junction_loader.project.directory
        else:
            directory = self._loader.project.directory
        file_path = os.path.join(directory, include)
        if file_path not in self._loaded:
            self._loaded[file_path] = _yaml.load(os.path.join(directory, include))
        return self._loaded[file_path]

    def _process_value(self, value):
        if isinstance(value, Mapping):
            self.process(value)
        elif isinstance(value, list):
            self._process_list(value)

    def _process_list(self, values):
        for value in values:
            self._process_value(value)
