#
#  Copyright (C) 2016 Codethink Limited
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

# Plugin author facing APIs
import os

if "_BST_COMPLETION" not in os.environ:

    # Special sauce to get the version from versioneer
    from ._version import get_versions

    __version__ = get_versions()["version"]
    del get_versions

    from .utils import UtilError, ProgramNotFoundError
    from .sandbox import Sandbox, SandboxFlags, SandboxCommandError
    from .types import Scope, CoreWarnings
    from .node import MappingNode, Node, ProvenanceInformation, ScalarNode, SequenceNode
    from .plugin import Plugin
    from .source import Source, SourceError, SourceFetcher
    from .downloadablefilesource import DownloadableFileSource
    from .element import Element, ElementError
    from .buildelement import BuildElement
    from .scriptelement import ScriptElement

    # XXX We are exposing a private member here as we expect it to move to a
    # separate package soon. See the following discussion for more details:
    # https://gitlab.com/BuildStream/buildstream/issues/739#note_124819869
    from ._gitsourcebase import _GitSourceBase, _GitMirror
