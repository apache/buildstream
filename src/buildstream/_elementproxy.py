#
#  Copyright (C) 2020 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
from typing import TYPE_CHECKING, cast, Optional, Iterator, Dict, List

from .types import Scope
from .utils import FileListResult
from ._pluginproxy import PluginProxy

if TYPE_CHECKING:
    from typing import Any
    from .node import MappingNode, ScalarNode, SequenceNode
    from .sandbox import Sandbox
    from .source import Source
    from .element import Element  # pylint: disable=cyclic-import


# ElementProxy()
#
# A PluginProxy for Element instances.
#
# Refer to the Element class for the documentation for these APIs.
#
class ElementProxy(PluginProxy):
    def __lt__(self, other):
        return self.name < other.name

    ##############################################################
    #                   Exposed proxied APIs                     #
    ##############################################################

    @property
    def project_name(self):
        return cast("Element", self._plugin).project_name

    @property
    def normal_name(self):
        return cast("Element", self._plugin).normal_name

    def sources(self) -> Iterator["Source"]:
        return cast("Element", self._plugin).sources()

    def dependencies(self, scope: Scope, *, recurse: bool = True, visited=None) -> Iterator["Element"]:
        #
        # FIXME: In the next phase, we will ensure that returned ElementProxy objects here are always
        # in the Scope.BUILD scope of the toplevel concrete Element class.
        #
        return cast("Element", self._plugin).dependencies(scope, recurse=recurse, visited=visited)

    def search(self, scope: Scope, name: str) -> Optional["Element"]:
        return cast("Element", self._plugin).search(scope, name)

    def node_subst_vars(self, node: "ScalarNode") -> str:
        return cast("Element", self._plugin).node_subst_vars(node)

    def node_subst_sequence_vars(self, node: "SequenceNode[ScalarNode]") -> List[str]:
        return cast("Element", self._plugin).node_subst_sequence_vars(node)

    def compute_manifest(
        self, *, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None, orphans: bool = True
    ) -> str:
        return cast("Element", self._plugin).compute_manifest(include=include, exclude=exclude, orphans=orphans)

    def get_artifact_name(self, key: Optional[str] = None) -> str:
        return cast("Element", self._plugin).get_artifact_name(key=key)

    def stage_artifact(
        self,
        sandbox: "Sandbox",
        *,
        path: str = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True
    ) -> FileListResult:
        return cast("Element", self._plugin).stage_artifact(
            sandbox, path=path, include=include, exclude=exclude, orphans=orphans
        )

    def stage_dependency_artifacts(
        self,
        sandbox: "Sandbox",
        scope: Scope,
        *,
        path: str = None,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True
    ) -> None:
        return cast("Element", self._plugin).stage_dependency_artifacts(
            sandbox, scope, path=path, include=include, exclude=exclude, orphans=orphans
        )

    def integrate(self, sandbox: "Sandbox") -> None:
        cast("Element", self._plugin).integrate(sandbox)

    def get_public_data(self, domain: str) -> "MappingNode[Any]":
        return cast("Element", self._plugin).get_public_data(domain)

    def get_environment(self) -> Dict[str, str]:
        return cast("Element", self._plugin).get_environment()

    def get_variable(self, varname: str) -> Optional[str]:
        return cast("Element", self._plugin).get_variable(varname)

    def get_logs(self) -> List[str]:
        return cast("Element", self._plugin).get_logs()
