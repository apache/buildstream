from typing import List

from ..node import Node, ScalarNode

def extract_depends_from_node(node: Node) -> List[Dependency]: ...

class Dependency: ...
class DependencyType: ...

class LoadElement:
    first_pass: bool
    kind: str
    name: str
    node: Node
    link_target: ScalarNode
