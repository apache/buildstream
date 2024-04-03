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
"""
SourceMirror - Base source mirror class
=======================================
The SourceMirror plugin allows one to customize how
:func:`Source.translate_url() <buildstream.source.Source.translate_url>` will
behave when looking up mirrors, allowing some additional flexibility in the
implementation of source mirrors.


.. _core_source_mirror_abstract_methods:

Abstract Methods
----------------
For loading and configuration purposes, SourceMirrors may optionally implement
the :func:`Plugin base class Plugin.configure() method <buildstream.plugin.Plugin.configure>`
in order to load any custom configuration in the `config` dictionary.

The remaining :ref:`Plugin base class abstract methods <core_plugin_abstract_methods>` are
not relevant to the SourceMirror plugin object and need not be implemented.

SourceMirrors expose the following abstract methods. Unless explicitly mentioned,
these methods are mandatory to implement.

* :func:`SourceMirror.translate_url() <buildstream.source.SourceMirror.translate_url>`
 
  Produce an appropriate URL for the given URL and alias.


Class Reference
---------------
"""

from typing import Optional, Any, Dict, List, Set, TYPE_CHECKING

from .node import MappingNode
from .plugin import Plugin
from ._exceptions import BstError, ImplError
from .exceptions import ErrorDomain

if TYPE_CHECKING:

    # pylint: disable=cyclic-import
    from ._context import Context
    from ._project import Project

    # pylint: enable=cyclic-import


class SourceMirrorError(BstError):
    """This exception should be raised by :class:`.SourceMirror` implementations
    to report errors to the user.

    Args:
       message: The breif error description to report to the user
       detail: A possibly multiline, more detailed error message
       reason: An optional machine readable reason string, used for test cases

    *Since: 2.2*
    """

    def __init__(
        self, message: str, *, detail: Optional[str] = None, reason: Optional[str] = None, temporary: bool = False
    ):
        super().__init__(message, detail=detail, domain=ErrorDomain.SOURCE, reason=reason)


class SourceMirror(Plugin):
    """SourceMirror()

    Base SourceMirror class.

    All SourceMirror plugins derive from this class, this interface defines how
    the core will be interacting with SourceMirror plugins.

    *Since: 2.2*
    """

    # The SourceMirror plugin type is only supported since BuildStream 2.2
    BST_MIN_VERSION = "2.2"

    def __init__(
        self,
        context: "Context",
        project: "Project",
        node: MappingNode,
    ):
        # Note: the MappingNode passed here is already expanded with
        #       the project level base variables, so there is no need
        #       to expand them redundantly here.
        #

        # Special case for the default plugin
        kind = node.get_str("kind", "default")
        if kind == "default":
            config_node = node
        else:
            node.validate_keys(["name", "kind", "config"])
            config_node = node.get_mapping("config", {})

        # Do local base class parsing first
        name: str = node.get_str("name")

        # Chain up to Plugin
        super().__init__(name, context, project, node, "source-mirror")

        self.__aliases: Set[str] = set()
        self._configure(config_node)

    ##########################################################
    #                      Internal API                      #
    ##########################################################

    # Returns a list of URIs/SourceMirrors for a given alias.
    def _get_alias_uris(self, alias: str) -> List:
        assert self.__aliases, "Didn't set aliases during configuring time"
        if alias in self.__aliases:
            return [self]
        return []

    ##########################################################
    #                        Public API                      #
    ##########################################################

    def set_supported_aliases(self, aliases: List[str]):
        """Set the aliases for which `self` can translate urls.

        Args:
           aliases: The list of aliases supported by this plugin
        """
        assert self._get_configuring(), "Trying to set aliases after configure time"
        self.__aliases.update(aliases)

    def translate_url(
        self,
        *,
        alias: str,
        alias_url: str,
        source_url: str,
        extra_data: Optional[Dict[str, Any]],
    ) -> str:
        """Produce an alternative url for `url` for the given alias.

        This method implements the behavior of :func:`Source.translate_url() <buildstream.source.Source.translate_url>`.

        Args:
           alias: The alias to translate for
           alias_url: The default URL configured for this alias in the originating project
           source_url: The URL as specified by original source YAML, excluding the alias
           extra_data: An optional extra dictionary to return additional data
        """
        raise ImplError(
            "source mirror plugin '{kind}' does not implement translate_url()".format(kind=self.get_kind())
        )
