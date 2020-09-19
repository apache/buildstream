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
from typing import TYPE_CHECKING, cast, Optional, Iterator, Dict, List, Sequence

from .types import _Scope, OverlapAction
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

    def dependencies(self, selection: Sequence["Element"] = None, *, recurse: bool = True) -> Iterator["Element"]:
        #
        # When dependencies() is called on a dependency of the main plugin Element,
        # we simply reroute the call to the original owning element, while specifying
        # this element as the selection.
        #
        # This ensures we only allow returning dependencies in the _Scope.RUN scope
        # of this element.
        #
        if selection is None:
            selection = [cast("Element", self._plugin)]

        # Return the iterable from the called generator, this is more performant than yielding from it
        return cast("Element", self._owner).dependencies(selection, recurse=recurse)

    def search(self, name: str) -> Optional["Element"]:
        #
        # Similarly to dependencies() above, we only search in the _Scope.RUN
        # of dependencies of the active element plugin.
        #
        return cast("Element", self._plugin)._search(_Scope.RUN, name)

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
        action: str = OverlapAction.WARNING,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True
    ) -> FileListResult:

        owner = cast("Element", self._owner)
        element = cast("Element", self._plugin)

        assert owner._overlap_collector is not None, "Attempted to stage artifacts outside of Element.stage()"

        with owner._overlap_collector.session(action, path):
            result = element._stage_artifact(
                sandbox, path=path, action=action, include=include, exclude=exclude, orphans=orphans, owner=owner
            )

        return result

    def stage_dependency_artifacts(
        self,
        sandbox: "Sandbox",
        selection: Sequence["Element"] = None,
        *,
        path: str = None,
        action: str = OverlapAction.WARNING,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True
    ) -> None:
        #
        # Same approach used here as in Element.dependencies()
        #
        if selection is None:
            selection = [cast("Element", self._plugin)]
        cast("Element", self._owner).stage_dependency_artifacts(
            sandbox, selection, path=path, action=action, include=include, exclude=exclude, orphans=orphans
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

    ##############################################################
    #                   Element Internal APIs                    #
    ##############################################################
    #
    # Some functions the Element expects to call directly on the
    # proxy.
    #
    def _dependencies(self, scope, *, recurse=True, visited=None):
        #
        # We use a return statement even though this is a generator, simply
        # to avoid the generator overhead of yielding each element.
        #
        return cast("Element", self._plugin)._dependencies(scope, recurse=recurse, visited=visited)

    def _file_is_whitelisted(self, path):
        return cast("Element", self._plugin)._file_is_whitelisted(path)

    def _stage_artifact(
        self,
        sandbox: "Sandbox",
        *,
        path: str = None,
        action: str = OverlapAction.WARNING,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        orphans: bool = True,
        owner: Optional["Element"] = None
    ) -> FileListResult:
        owner = cast("Element", self._owner)
        element = cast("Element", self._plugin)
        return element._stage_artifact(
            sandbox, path=path, action=action, include=include, exclude=exclude, orphans=orphans, owner=owner
        )
