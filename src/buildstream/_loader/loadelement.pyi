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
from buildstream._loader.loader import Loader
import enum
from buildstream._project import Project
from typing import List, Optional

from buildstream.plugins.elements.junction import JunctionElement
from buildstream.node import Node, ScalarNode, MappingNode, SequenceNode

def extract_depends_from_node(node: Node) -> List[Dependency]:
    """
    extract_depends_from_node():

    Creates an array of Dependency objects from a given dict node 'node',
    allows both strings and dicts for expressing the dependency and
    throws a comprehensive LoadError in the case that the node is malformed.

    After extracting depends, the symbol is deleted from the node

    Args:
    node (Node): A YAML loaded dictionary

    Returns:
    (list): a list of Dependency objects
    """
    ...

def sort_dependencies(element: LoadElement, visited: set[LoadElement]):
    """
    sort_dependencies():

    Sort dependencies of each element by their dependencies,
    so that direct dependencies which depend on other direct
    dependencies (directly or indirectly) appear later in the
    list.

    This avoids the need for performing multiple topological
    sorts throughout the build process.

    Args:
    element (LoadElement): The element to sort
    visited (set): a list of elements that should not be treated because
                    because they already have been treated.
                    This is useful when wanting to sort dependencies of
                    multiple top level elements that might have a common
                    part.
    """
    ...

class Dependency:
    """
    Dependency():

    Early stage data model for dependencies objects, the LoadElement has
    Dependency objects which in turn refer to other LoadElements in the data
    model.

    The constructor is incomplete, normally dependencies are loaded
    via the Dependency.load() API below. The constructor arguments are
    only used as a convenience to create the dummy Dependency objects
    at the toplevel of the load sequence in the Loader.

    Args:
        element (LoadElement): a LoadElement on which there is a dependency
        dep_type (DependencyType): the type of dependency this dependency link is
    """

    name: str
    """
    The project local dependency name
    """
    node: Node
    """
    The original node of the dependency
    """
    element: LoadElement
    """
    The resolved LoadElement
    """
    dep_type: DependencyType
    """
    The dependency type (runtime or build or both)
    """
    junction: Optional[str]
    """
    The junction path of the dependency name, if any
    """
    config_nodes: List[MappingNode]
    """
    The custom config nodes for Element.configure_dependencies()
    """
    strict: bool
    """
    Whether this is a strict dependency
    """

    path: str
    """
    The path of the dependency represented as a single string,
    instead of junction and name being separate.
    """

    def __init__(self, element: LoadElement, dep_type: DependencyType):
        """
        Dependency():

        Early stage data model for dependencies objects, the LoadElement has
        Dependency objects which in turn refer to other LoadElements in the data
        model.

        The constructor is incomplete, normally dependencies are loaded
        via the Dependency.load() API below. The constructor arguments are
        only used as a convenience to create the dummy Dependency objects
        at the toplevel of the load sequence in the Loader.

        Args:
            element (LoadElement): a LoadElement on which there is a dependency
            dep_type (DependencyType): the type of dependency this dependency link is
        """

    def set_element(self, element: LoadElement) -> None:
        """
        set_element()

        Sets the resolved LoadElement

        When Dependencies are initially loaded, the `element` member
        will be None until later on when the Loader loads the LoadElement
        objects based on the Dependency `name` and `junction`, the Loader
        will then call this to resolve the `element` member.

        Args:
        element (LoadElement): The resolved LoadElement
        """

    def merge(self, other: Dependency) -> None:
        """
        merge()

        Merge the attributes of an existing dependency into this dependency

        Args:
        other (Dependency): The dependency to merge into this one
        """

class DependencyType(enum.Enum):
    """
    DependencyType

    A bitfield to represent dependency types
    """

    BUILD = 0x001
    """
    A build dependency
    """
    RUNTIME = 0x002
    """
    A runtime dependency
    """
    ALL = 0x003
    """
    Both build and runtime dependencies
    """

class LoadElement:
    """
    LoadElement():

    A transient object breaking down what is loaded allowing us to
    do complex operations in multiple passes.

    Args:
    node (dict): A YAML loaded dictionary
    name (str): The element name
    loader (Loader): The Loader object for this element
    """

    first_pass: bool
    """
    Whether the element should be included in a first pass when processing

    e.g. link or junction elements that need resolving before usage.
    """
    kind: str
    """
    The Element kind
    """
    name: str
    """
    The element name
    """
    full_name: str
    """
    The element full name (with associated junction)
    """
    description: str
    """
    The element description
    """
    node: MappingNode
    """
    The YAML node
    """
    link_target: ScalarNode
    """
    The target of a link element (ScalarNode)
    """
    fully_loaded: bool
    """
    Whether we entered the loop to load dependencies or not
    """

    project: "Project"
    """
    The Project the Element is from
    """
    junction: Optional[JunctionElement]
    """
    The Optional JunctionElement the Element is from
    """
    dependencies: List[Dependency]
    """
    The Element dependencies
    """

    def __init__(self, node: MappingNode, filename: str, loader: Loader):
        """
        LoadElement():

        A transient object breaking down what is loaded allowing us to
        do complex operations in multiple passes.

        Args:
        node (dict): A YAML loaded dictionary
        name (str): The element name
        loader (Loader): The Loader object for this element
        """

    def mark_fully_loaded(self): ...
