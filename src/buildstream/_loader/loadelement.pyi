from typing import List

from ..node import Node, ProvenanceInformation

def extract_depends_from_node(node: Node) -> List[Dependency]: ...

class Dependency: ...
class DependencyType: ...

class LoadElement:
    first_pass: bool
    kind: str
    name: str
    provenance: ProvenanceInformation
