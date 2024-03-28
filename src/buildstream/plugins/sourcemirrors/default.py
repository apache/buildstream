from typing import Optional, Dict, List, Any, TYPE_CHECKING

from buildstream import SourceMirror, MappingNode, SequenceNode, SourceMirrorError


class AliasesSourceMirror(SourceMirror):
    BST_MIN_VERSION = "2.1"  # temporary

    def configure(self, node: MappingNode) -> None:
        node.validate_keys(SourceMirror.COMMON_CONFIG_KEYS + ["aliases"])
        self._aliases: Dict[str, List[str]] = self._load_aliases(node)

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
    return AliasesSourceMirror
