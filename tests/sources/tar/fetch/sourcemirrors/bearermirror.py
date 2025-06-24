from typing import Optional, Dict, Any

from buildstream import SourceMirror, MappingNode


class Sample(SourceMirror):
    def configure(self, node):
        node.validate_keys(["aliases"])

        self.aliases = {}

        aliases = node.get_mapping("aliases")
        for alias_name, url_list in aliases.items():
            self.aliases[alias_name] = url_list.as_str_list()

        self.set_supported_aliases(self.aliases.keys())

    def translate_url(
        self,
        *,
        alias: str,
        alias_url: str,
        source_url: str,
        extra_data: Optional[Dict[str, Any]],
    ) -> str:
        if extra_data is not None:
            extra_data["http-auth"] = "bearer"

        return self.aliases[alias][0] + source_url


# Plugin entry point
def setup():
    return Sample
