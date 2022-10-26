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
    from .sandbox import Sandbox, SandboxCommandError
    from .storage import Directory, DirectoryError, FileType, FileStat
    from .types import CoreWarnings, OverlapAction, FastEnum, SourceRef
    from .node import MappingNode, Node, ProvenanceInformation, ScalarNode, SequenceNode
    from .plugin import Plugin
    from .source import Source, SourceError, SourceFetcher
    from .downloadablefilesource import DownloadableFileSource
    from .element import Element, ElementError, DependencyConfiguration
    from .buildelement import BuildElement
    from .scriptelement import ScriptElement
