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
#        Abderrahim Kitouni <abderrahim.kitouni@codethink.co.uk>

from typing import Optional, Dict, List, Any, TYPE_CHECKING

from buildstream import SourceMirror, MappingNode, SequenceNode, SourceMirrorError


class DefaultSourceMirror(SourceMirror):
    def configure(self, node: MappingNode) -> None:
        node.validate_keys(["name", "kind", "aliases"])
        self._aliases = self._load_aliases(node)

    def _get_alias_uris(self, alias):
        if alias in self._aliases:
            return self._aliases[alias]

        return []

    def _load_aliases(self, node: MappingNode) -> Dict[str, List[str]]:
        aliases: Dict[str, List[str]] = {}
        alias_node: MappingNode = node.get_mapping("aliases")

        for alias, uris in alias_node.items():
            aliases[alias] = uris.as_str_list()

        return aliases


def setup():
    return DefaultSourceMirror
