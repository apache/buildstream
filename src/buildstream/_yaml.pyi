from typing import Optional

from .node import MappingNode

def load(filename: str, shortname: str, copy_tree: bool = False, project: Optional[object] = None) -> MappingNode: ...
