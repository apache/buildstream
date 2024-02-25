from typing import Optional, Dict, Any

from buildstream import SourceMirror, MappingNode


# This mirror plugin basically implements the default behavior
# by loading the alias definitions as custom "config" configuration
# instead, and implementing the translate_url method.
#
class Sample(SourceMirror):
    BST_MIN_VERSION = "2.0"

    def configure(self, node):
        node.validate_keys(["aliases"])

        self.aliases = {}

        aliases = node.get_mapping("aliases")
        for alias_name, url_list in aliases.items():
            self.aliases[alias_name] = url_list.as_str_list()

    def translate_url(
        self,
        *,
        project_name: str,
        alias: str,
        alias_url: str,
        alias_substitute_url: Optional[str],
        source_url: str,
        extra_data: Optional[Dict[str, Any]],
    ) -> str:
        return self.aliases[alias][0] + source_url


# Plugin entry point
def setup():

    return Sample
