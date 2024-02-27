from typing import Optional, Dict, Any

from buildstream import SourceMirror, MappingNode


class Sample(SourceMirror):
    BST_MIN_VERSION = "2.0"

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

        if extra_data is not None:
            extra_data["auth-header-format"] = "Bearer {password}"

        return alias_substitute_url + source_url


# Plugin entry point
def setup():

    return Sample
