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
Source - Base source class
==========================

.. _core_source_builtins:

Built-in functionality
----------------------

The Source base class provides built in functionality that may be overridden
by individual plugins.

* Directory

  The ``directory`` variable can be set for all sources of a type in project.conf
  or per source within a element.

  This sets the location within the build root that the content of the source
  will be loaded in to. If the location does not exist, it will be created.

.. _core_source_abstract_methods:

Abstract Methods
----------------
For loading and configuration purposes, Sources must implement the
:ref:`Plugin base class abstract methods <core_plugin_abstract_methods>`.

.. attention::

   In order to ensure that all configuration data is processed at
   load time, it is important that all URLs have been processed during
   :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`.

   Source implementations *must* either call
   :func:`Source.translate_url() <buildstream.source.Source.translate_url>` or
   :func:`Source.mark_download_url() <buildstream.source.Source.mark_download_url>`
   for every URL that has been specified in the configuration during
   :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`

Sources expose the following abstract methods. Unless explicitly mentioned,
these methods are mandatory to implement.

* :func:`Source.load_ref() <buildstream.source.Source.load_ref>`

  Load the ref from a specific YAML node

* :func:`Source.get_ref() <buildstream.source.Source.get_ref>`

  Fetch the source ref

* :func:`Source.set_ref() <buildstream.source.Source.set_ref>`

  Set a new ref explicitly

* :func:`Source.track() <buildstream.source.Source.track>`

  Automatically derive a new ref from a symbolic tracking branch

* :func:`Source.fetch() <buildstream.source.Source.fetch>`

  Fetch the actual payload for the currently set ref

* :func:`Source.stage() <buildstream.source.Source.stage>` / :func:`Source.stage_directory() <buildstream.source.Source.stage_directory>`

  Stage the sources for a given ref at a specified location

* :func:`Source.init_workspace() <buildstream.source.Source.init_workspace>` / :func:`Source.init_workspace_workspace() <buildstream.source.Source.init_workspace_directory>`

  Stage sources for use as a workspace.

  **Optional**: If left unimplemented, these will default to calling
  :func:`Source.stage() <buildstream.source.Source.stage>` / :func:`Source.stage_directory() <buildstream.source.Source.stage_directory>`

* :func:`Source.get_source_fetchers() <buildstream.source.Source.get_source_fetchers>`

  Get the objects that are used for fetching.

  **Optional**: This only needs to be implemented for sources that need to
  download from multiple URLs while fetching (e.g. a git repo and its
  submodules). For details on how to define a SourceFetcher, see
  :ref:`SourceFetcher <core_source_fetcher>`.

* :func:`Source.validate_cache() <buildstream.source.Source.validate_cache>`

  Perform any validations which require the sources to be cached.

  **Optional**: This is completely optional and will do nothing if left unimplemented.


.. _core_source_ref:

Working with the source ref
---------------------------
The :attr:`~buildstream.types.SourceRef` is used to determine the exact
version of data to be addressed by the source.

The various responsibilities involving the source reference are described here.


Loading and saving
~~~~~~~~~~~~~~~~~~
The source reference is expected to be loaded at
:func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` and
and :func:`Source.load_ref() <buildstream.source.Source.load_ref>` time
from the provided :class:`.MappingNode`.

The :attr:`~buildstream.types.SourceRef` should be loaded from a `single key`
in that node, the recommended name for that key is `ref`, but is ultimately up
to the implementor to decide.

When :func:`Source.set_ref() <buildstream.source.Source.set_ref>` is called,
the source reference should be assigned to the `same single key` in the
provided :class:`.MappingNode`, this will be used to serialize changed
source references to YAML as a result of :ref:`tracking <invoking_source_track>`.


Tracking new references
~~~~~~~~~~~~~~~~~~~~~~~
When the user :ref:`tracks <invoking_source_track>` for new versions of the source,
then the new :attr:`~buildstream.types.SourceRef` should be returned from
the :func:`Source.track() <buildstream.source.Source.track>` implementation.


Managing internal state
~~~~~~~~~~~~~~~~~~~~~~~
Internally the source implementation is expected to keep track of its
:attr:`~buildstream.types.SourceRef`. The internal state should be
updated when :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`,
:func:`Source.load_ref() <buildstream.source.Source.load_ref>` or
:func:`Source.set_ref() <buildstream.source.Source.set_ref>` is called.

The internal state should not be updated when
:func:`Source.track() <buildstream.source.Source.track>` is called.

The internal source ref must be returned on demand whenever
:func:`Source.get_ref() <buildstream.source.Source.get_ref>` is called.


Generating the unique key
~~~~~~~~~~~~~~~~~~~~~~~~~
When :func:`Plugin.get_unique_key() <buildstream.plugin.Plugin.get_unique_key>`
is called, the source's :attr:`~buildstream.types.SourceRef` must be considered
as a part of that key.

The unique key will be used to generate the cache key of :ref:`cache keys <cachekeys>`
of elements using this source, and so the unique key should be comprised of every
configuration which may effect how the source is :func:`staged <buildstream.source.Source.stage>`,
as well as any configuration which uniquely identifies the source, which of course
includes the :attr:`~buildstream.types.SourceRef`.


Accessing previous sources
--------------------------
In the general case, all sources are fetched and tracked independently of one
another. In situations where a source needs to access previous source(s) in
order to perform its own track and/or fetch, following attributes can be set to
request access to previous sources:

* :attr:`~buildstream.source.Source.BST_REQUIRES_PREVIOUS_SOURCES_TRACK`

  Indicate that access to previous sources is required during track

* :attr:`~buildstream.source.Source.BST_REQUIRES_PREVIOUS_SOURCES_FETCH`

  Indicate that access to previous sources is required during fetch

The intended use of such plugins is to fetch external dependencies of other
sources, typically using some kind of package manager, such that all the
dependencies of the original source(s) are available at build time.

When implementing such a plugin, implementors should adhere to the following
guidelines:

* Implementations must be able to store the obtained artifacts in a
  subdirectory.

* Implementations must be able to deterministically generate a unique ref, such
  that two refs are different if and only if they produce different outputs.

* Implementations must not introduce host contamination.


.. _core_source_fetcher:

SourceFetcher - Object for fetching individual URLs
===================================================


Abstract Methods
----------------
SourceFetchers expose the following abstract methods. Unless explicitly
mentioned, these methods are mandatory to implement.

* :func:`SourceFetcher.fetch() <buildstream.source.SourceFetcher.fetch>`

  Fetches the URL associated with this SourceFetcher, optionally taking an
  alias override.

Class Reference
---------------
"""

import os
from contextlib import contextmanager
from typing import Iterable, Iterator, Optional, Tuple, TYPE_CHECKING

from . import _yaml, utils
from .node import MappingNode
from .plugin import Plugin
from .types import SourceRef, CoreWarnings
from ._exceptions import BstError, ImplError, PluginError
from .exceptions import ErrorDomain
from ._loader.metasource import MetaSource
from ._projectrefs import ProjectRefStorage
from ._cachekey import generate_key
from .storage import CasBasedDirectory
from .storage import FileBasedDirectory
from .storage.directory import Directory
from ._variables import Variables

if TYPE_CHECKING:
    from typing import Any, Dict, Set

    # pylint: disable=cyclic-import
    from ._context import Context
    from ._project import Project

    # pylint: enable=cyclic-import


class SourceError(BstError):
    """This exception should be raised by :class:`.Source` implementations
    to report errors to the user.

    Args:
       message: The breif error description to report to the user
       detail: A possibly multiline, more detailed error message
       reason: An optional machine readable reason string, used for test cases
       temporary: An indicator to whether the error may occur if the operation was run again.
    """

    def __init__(
        self, message: str, *, detail: Optional[str] = None, reason: Optional[str] = None, temporary: bool = False
    ):
        super().__init__(message, detail=detail, domain=ErrorDomain.SOURCE, reason=reason, temporary=temporary)


class SourceFetcher:
    """SourceFetcher()

    This interface exists so that a source that downloads from multiple
    places (e.g. a git source with submodules) has a consistent interface for
    fetching and substituting aliases.

    .. attention::

       When implementing a SourceFetcher, remember to call
       :func:`Source.mark_download_url() <buildstream.source.Source.mark_download_url>`
       for every URL found in the configuration data at
       :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` time.
    """

    def __init__(self):
        self.__alias = None

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def fetch(self, alias_override: Optional[str] = None, **kwargs) -> None:
        """Fetch remote sources and mirror them locally, ensuring at least
        that the specific reference is cached locally.

        Args:
           alias_override: The alias to use instead of the default one
               defined by the :ref:`aliases <project_source_aliases>` field
               in the project's config.

        Raises:
           :class:`.SourceError`

        Implementors should raise :class:`.SourceError` if the there is some
        network error or if the source reference could not be matched.
        """
        raise ImplError("SourceFetcher '{}' does not implement fetch()".format(type(self)))

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def mark_download_url(self, url: str) -> None:
        """Identifies the URL that this SourceFetcher uses to download

        This must be called during the fetcher's initialization

        Args:
           url: The url used to download.
        """
        self.__alias = _extract_alias(url)

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # Returns the alias used by this fetcher
    def _get_alias(self):
        return self.__alias


class Source(Plugin):
    """Source()

    Base Source class.

    All Sources derive from this class, this interface defines how
    the core will be interacting with Sources.
    """

    # The defaults from the project
    __defaults = None  # type: Optional[Dict[str, Any]]

    BST_REQUIRES_PREVIOUS_SOURCES_TRACK = False
    """Whether access to previous sources is required during track

    When set to True:
      * all sources listed before this source in the given element will be
        fetched before this source is tracked
      * Source.track() will be called with an additional keyword argument
        `previous_sources_dir` where previous sources will be staged
      * this source can not be the first source for an element
    """

    BST_REQUIRES_PREVIOUS_SOURCES_FETCH = False
    """Whether access to previous sources is required during fetch

    When set to True:
      * all sources listed before this source in the given element will be
        fetched before this source is fetched
      * Source.fetch() will be called with an additional keyword argument
        `previous_sources_dir` where previous sources will be staged
      * this source can not be the first source for an element
    """

    BST_REQUIRES_PREVIOUS_SOURCES_STAGE = False
    """Whether access to previous sources is required during cache

    When set to True:
      * All sources listed before current source in the given element will be
        staged with the source when it's cached.
      * This source can not be the first source for an element.
    """

    BST_STAGE_VIRTUAL_DIRECTORY = False
    """Whether we can stage this source directly to a virtual directory

    When set to True, :func:`Source.stage_directory() <buildstream.source.Source.stage_directory>`
    and :func:`Source.init_workspace_directory() <buildstream.source.Source.init_workspace_directory>`
    will be called in place of :func:`Source.stage() <buildstream.source.Source.stage>` and
    :func:`Source.init_workspace() <buildstream.source.Source.init_workspace>` respectively.
    """

    def __init__(
        self,
        context: "Context",
        project: "Project",
        meta: MetaSource,
        variables: Variables,
        *,
        alias_override: Optional[Tuple[str, str]] = None,
        unique_id: Optional[int] = None
    ):
        # Set element_name member before parent init, as needed for debug messaging
        self.__element_name = meta.element_name  # The name of the element owning this source
        super().__init__(
            "{}-{}".format(meta.element_name, meta.element_index),
            context,
            project,
            meta.config,
            "source",
            unique_id=unique_id,
        )

        self.__element_index = meta.element_index  # The index of the source in the owning element's source list
        self.__element_kind = meta.element_kind  # The kind of the element owning this source
        self._directory = meta.directory  # Staging relative directory
        self.__variables = variables  # The variables used to resolve the source's config

        self.__key = None  # Cache key for source

        # The alias_override is only set on a re-instantiated Source
        self.__alias_override = alias_override  # Tuple of alias and its override to use instead
        self.__expected_alias = None  # The primary alias
        # Set of marked download URLs
        self.__marked_urls = set()  # type: Set[str]

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__init_defaults(project, meta)
        self.__config = self.__extract_config(meta)
        variables.expand(self.__config)

        self.__first_pass = meta.first_pass

        # cached values for commonly access values on the source
        self.__mirror_directory = None  # type: Optional[str]

        self._configure(self.__config)

        self.__is_cached = None

    COMMON_CONFIG_KEYS = ["kind", "directory"]
    """Common source config keys

    Source config keys that must not be accessed in configure(), and
    should be checked for using node.validate_keys().
    """

    #############################################################
    #                      Abstract Methods                     #
    #############################################################

    def load_ref(self, node: MappingNode) -> None:
        """Loads the :attr:`~buildstream.types.SourceRef` for this Source from the specified *node*.

        Args:
           node: The YAML node to load the ref from

        Working with the :ref:`source ref is discussed here <core_source_ref>`.

        .. note::

           The :attr:`~buildstream.types.SourceRef` for the Source is expected to be read at
           :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` time,
           this will only be used for loading refs from alternative locations
           than in the `element.bst` file where the given Source object has
           been declared.
        """
        raise ImplError("Source plugin '{}' does not implement load_ref()".format(self.get_kind()))

    def get_ref(self) -> SourceRef:
        """Fetch the :attr:`~buildstream.types.SourceRef`

        Returns:
           The internal :attr:`~buildstream.types.SourceRef`, or ``None``

        Working with the :ref:`source ref is discussed here <core_source_ref>`.
        """
        raise ImplError("Source plugin '{}' does not implement get_ref()".format(self.get_kind()))

    def set_ref(self, ref: SourceRef, node: MappingNode) -> None:
        """Applies the internal ref, however it is represented

        Args:
           ref: The internal :attr:`~buildstream.types.SourceRef` to set, or ``None``
           node: The same node which was previously passed
                 to :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`
                 and :func:`Source.load_ref() <buildstream.source.Source.load_ref>`

        The implementor must update the *node* parameter to reflect the new *ref*,
        and it should store the passed *ref* so that it will be returned in any
        later calls to :func:`Source.get_ref() <buildstream.source.Source.get_ref>`.

        The passed *ref* parameter is guaranteed to either be a value which has
        been previously retrieved by the :func:`Source.get_ref() <buildstream.source.Source.get_ref>`
        method on the same plugin, or ``None``.

        **Example:**

        .. code:: python

           # Implementation of Source.set_ref()
           #
           def set_ref(self, ref, node):

               # Update internal state of the ref
               self.ref = ref

               # Update the passed node so that we will read the new ref
               # next time this source plugin is configured with this node.
               #
               node["ref"] = self.ref

        Working with the :ref:`source ref is discussed here <core_source_ref>`.
        """
        raise ImplError("Source plugin '{}' does not implement set_ref()".format(self.get_kind()))

    def track(self, *, previous_sources_dir: str = None) -> SourceRef:
        """Resolve a new ref from the plugin's track option

        Args:
           previous_sources_dir (str): directory where previous sources are staged.
                                       Note that this keyword argument is available only when
                                       :attr:`~buildstream.source.Source.BST_REQUIRES_PREVIOUS_SOURCES_TRACK`
                                       is set to True.

        Returns:
           A new :attr:`~buildstream.types.SourceRef`, or None

        If the backend in question supports resolving references from
        a symbolic tracking branch or tag, then this should be implemented
        to perform this task on behalf of :ref:`bst source track <invoking_source_track>`
        commands.

        This usually requires fetching new content from a remote origin
        to see if a new ref has appeared for your branch or tag. If the
        backend store allows one to query for a new ref from a symbolic
        tracking data without downloading then that is desirable.

        Working with the :ref:`source ref is discussed here <core_source_ref>`.
        """
        # Allow a non implementation
        return None

    def fetch(self, *, previous_sources_dir: str = None) -> None:
        """Fetch remote sources and mirror them locally, ensuring at least
        that the specific reference is cached locally.

        Args:
           previous_sources_dir (str): directory where previous sources are staged.
                                       Note that this keyword argument is available only when
                                       :attr:`~buildstream.source.Source.BST_REQUIRES_PREVIOUS_SOURCES_FETCH`
                                       is set to True.

        Raises:
           :class:`.SourceError`

        Implementors should raise :class:`.SourceError` if the there is some
        network error or if the source reference could not be matched.
        """
        raise ImplError("Source plugin '{}' does not implement fetch()".format(self.get_kind()))

    def stage(self, directory: str) -> None:
        """Stage the sources to a directory

        Args:
           directory: Path to stage the source

        Raises:
           :class:`.SourceError`

        Implementors should assume that *directory* already exists
        and stage already cached sources to the passed directory.

        Implementors should raise :class:`.SourceError` when encountering
        some system error.
        """
        raise ImplError("Source plugin '{}' does not implement stage()".format(self.get_kind()))

    def stage_directory(self, directory: Directory) -> None:
        """Stage the sources to a directory

        Args:
           directory: :class:`.Directory` object to stage the source into

        Raises:
           :class:`.SourceError`

        Implementors should assume that *directory* represents an existing
        directory root into which the source content can be populated.

        Implementors should raise :class:`.SourceError` when encountering
        some system error.

        .. note::

           This will be called *instead* of :func:`Source.stage() <buildstream.source.Source.stage>`
           in the case that :attr:`~buildstream.source.Source.BST_STAGE_VIRTUAL_DIRECTORY` is set
           for this plugin.
        """
        raise ImplError("Source plugin '{}' does not implement stage_directory()".format(self.get_kind()))

    def init_workspace(self, directory: str) -> None:
        """Stage sources for use as a workspace.

        Args:
           directory: Path of the workspace to initialize.

        Raises:
           :class:`.SourceError`

        Default implementation is to call
        :func:`Source.stage() <buildstream.source.Source.stage>`.

        Implementors overriding this method should assume that *directory*
        already exists.

        Implementors should raise :class:`.SourceError` when encountering
        some system error.
        """
        self.stage(directory)

    def init_workspace_directory(self, directory: Directory) -> None:
        """Stage sources for use as a workspace.

        Args:
           directory: :class:`.Directory` object of the workspace to initialize.

        Raises:
           :class:`.SourceError`

        Default implementation is to call
        :func:`Source.stage_directory() <buildstream.source.Source.stage_directory>`.

        Implementors overriding this method should assume that *directory*
        already exists.

        Implementors should raise :class:`.SourceError` when encountering
        some system error.

        .. note::

           This will be called *instead* of
           :func:`Source.init_workspace() <buildstream.source.Source.init_workspace>` in the case that
           :attr:`~buildstream.source.Source.BST_STAGE_VIRTUAL_DIRECTORY` is set for this plugin.
        """
        self.stage_directory(directory)

    def get_source_fetchers(self) -> Iterable[SourceFetcher]:
        """Get the objects that are used for fetching

        If this source doesn't download from multiple URLs,
        returning None and falling back on the default behaviour
        is recommended.

        Returns:
           The Source's SourceFetchers, if any.

        .. note::

           Implementors can implement this as a generator.

           The :func:`SourceFetcher.fetch() <buildstream.source.SourceFetcher.fetch>`
           method will be called on the returned fetchers one by one,
           before consuming the next fetcher in the list.
        """
        return []

    def validate_cache(self) -> None:
        """Implement any validations once we know the sources are cached

        This is guaranteed to be called only once for a given session
        once the sources are known to be cached, before
        :func:`Source.stage() <buildstream.source.Source.stage>` or
        :func:`Source.init_workspace() <buildstream.source.Source.init_workspace>`
        is called.
        """

    def is_cached(self) -> bool:
        """Get whether the source has a local copy of its data.

        This method is guaranteed to only be called whenever
        :func:`Source.is_resolved() <buildstream.source.Source.is_resolved>`
        returns `True`.

        Returns: whether the source is cached locally or not.
        """
        raise ImplError("Source plugin '{}' does not implement is_cached()".format(self.get_kind()))

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def get_mirror_directory(self) -> str:
        """Fetches the directory where this source should store things

        Returns:
           The directory belonging to this source
        """
        if self.__mirror_directory is None:
            # Create the directory if it doesnt exist
            context = self._get_context()
            directory = os.path.join(context.sourcedir, self.get_kind())
            os.makedirs(directory, exist_ok=True)
            self.__mirror_directory = directory

        return self.__mirror_directory

    def translate_url(self, url: str, *, alias_override: Optional[str] = None, primary: bool = True) -> str:
        """Translates the given url which may be specified with an alias
        into a fully qualified url.

        Args:
           url: A URL, which may be using an alias
           alias_override: Optionally, an URI to override the alias with.
           primary: Whether this is the primary URL for the source.

        Returns:
           The fully qualified URL, with aliases resolved
        .. note::

           This must be called for every URL in the configuration during
           :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` if
           :func:`Source.mark_download_url() <buildstream.source.Source.mark_download_url>`
           is not called.
        """
        # Ensure that the download URL is also marked
        self.mark_download_url(url, primary=primary)

        # Alias overriding can happen explicitly (by command-line) or
        # implicitly (the Source being constructed with an __alias_override).
        if alias_override or self.__alias_override:
            url_alias, url_body = url.split(utils._ALIAS_SEPARATOR, 1)
            if url_alias:
                if alias_override:
                    url = alias_override + url_body
                else:
                    # Implicit alias overrides may only be done for one
                    # specific alias, so that sources that fetch from multiple
                    # URLs and use different aliases default to only overriding
                    # one alias, rather than getting confused.
                    override_alias = self.__alias_override[0]  # type: ignore
                    override_url = self.__alias_override[1]  # type: ignore
                    if url_alias == override_alias:
                        url = override_url + url_body
            return url
        else:
            project = self._get_project()
            return project.translate_url(url, first_pass=self.__first_pass)

    def mark_download_url(self, url: str, *, primary: bool = True) -> None:
        """Identifies the URL that this Source uses to download

        Args:
           url (str): The URL used to download
           primary (bool): Whether this is the primary URL for the source

        .. note::

           This must be called for every URL in the configuration during
           :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` if
           :func:`Source.translate_url() <buildstream.source.Source.translate_url>`
           is not called.
        """
        # Only mark the Source level aliases on the main instance, not in
        # a reinstantiated instance in mirroring.
        if not self.__alias_override:
            if primary:
                expected_alias = _extract_alias(url)

                assert (
                    self.__expected_alias is None or self.__expected_alias == expected_alias
                ), "Primary URL marked twice with different URLs"

                self.__expected_alias = expected_alias

        # Enforce proper behaviour of plugins by ensuring that all
        # aliased URLs have been marked at Plugin.configure() time.
        #
        if self._get_configuring():
            # Record marked urls while configuring
            #
            self.__marked_urls.add(url)
        else:
            # If an unknown aliased URL is seen after configuring,
            # this is an error.
            #
            # It is still possible that a URL that was not mentioned
            # in the element configuration can be marked, this is
            # the case for git submodules which might be automatically
            # discovered.
            #
            assert url in self.__marked_urls or not _extract_alias(
                url
            ), "URL was not seen at configure time: {}".format(url)

        alias = _extract_alias(url)

        # Issue a (fatal-able) warning if the source used a URL without specifying an alias
        if not alias:
            self.warn(
                "{}: Use of unaliased source download URL: {}".format(self, url),
                warning_token=CoreWarnings.UNALIASED_URL,
            )

        # If there is an alias in use, ensure that it exists in the project
        if alias:
            project = self._get_project()
            if not project.alias_exists(alias, first_pass=self.__first_pass):
                raise SourceError(
                    "{}: Invalid alias '{}' specified in URL: {}".format(self, alias, url),
                    reason="invalid-source-alias",
                )

    def get_project_directory(self) -> str:
        """Fetch the project base directory

        This is useful for sources which need to load resources
        stored somewhere inside the project.

        Returns:
           The project base directory
        """
        project = self._get_project()
        return project.directory

    @contextmanager
    def tempdir(self) -> Iterator[str]:
        """Context manager for working in a temporary directory

        Yields:
           A path to a temporary directory

        This should be used by source plugins directly instead of the tempfile
        module. This one will automatically cleanup in case of termination by
        catching the signal before os._exit(). It will also use the 'mirror
        directory' as expected for a source.
        """
        mirrordir = self.get_mirror_directory()
        with utils._tempdir(dir=mirrordir) as tempdir:
            yield tempdir

    def is_resolved(self) -> bool:
        """Get whether the source is resolved.

        This has a default implementation that checks whether the source
        has a ref or not. If it has a ref, it is assumed to be resolved.

        Sources that never have a ref or have uncommon requirements can
        override this method to specify when they should be considered
        resolved

        Returns: whether the source is fully resolved or not
        """
        return self.get_ref() is not None

    #############################################################
    #       Private Abstract Methods used in BuildStream        #
    #############################################################

    # Returns the local path to the source
    #
    # If the source is locally available, this method returns the absolute
    # path. Otherwise, the return value is None.
    #
    # This is an optimization for local sources and optional to implement.
    #
    # Returns:
    #    (str): The local absolute path, or None
    #
    def _get_local_path(self):
        return None

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # Wrapper around preflight() method
    #
    def _preflight(self):
        try:
            self.preflight()
        except BstError as e:
            # Prepend provenance to the error
            raise SourceError("{}: {}".format(self, e), reason=e.reason) from e

    # Get whether the source is cached by the source plugin
    #
    def _is_cached(self):
        if self.__is_cached is None:
            # We guarantee we only ever call this when we are resolved.
            assert self.is_resolved()

            # Set to 'False' on the first call, this prevents throwing multiple errors if the
            # plugin throws exception when we display the end result pipeline.
            # Otherwise, the summary would throw a second exception and we would not
            # have a nice error reporting.
            self.__is_cached = False

            try:
                self.__is_cached = self.is_cached()  # pylint: disable=assignment-from-no-return
            except SourceError:
                # SourceErrors should be preserved so that the
                # plugin can communicate real error cases.
                raise
            except Exception as err:
                # Generic errors point to bugs in the plugin, so
                # we need to catch them and make sure they do not
                # cause stacktraces

                raise PluginError(
                    "Source plugin '{}' failed to check its cached state: {}".format(self.get_kind(), err),
                    reason="source-bug",
                )

        return self.__is_cached

    # Wrapper function around plugin provided fetch method
    #
    # Args:
    #   previous_sources_dir (str): directory where previous sources are staged
    #
    def _fetch(self, previous_sources_dir=None):
        if self.BST_REQUIRES_PREVIOUS_SOURCES_FETCH:
            self.__do_fetch(previous_sources_dir=previous_sources_dir)
        else:
            self.__do_fetch()

    # _fetch_done()
    #
    # Indicates that fetching the source has been done.
    #
    # Args:
    #   fetched_original (bool): Whether the original sources had been asked (and fetched) or not
    #
    def _fetch_done(self, fetched_original):
        if fetched_original:
            # The original was fetched, we know we are cached
            self.__is_cached = True
        else:
            # The original was not requested, we might or might not be cached
            # Don't recompute, but allow recomputation later if needed
            self.__is_cached = None

    # Wrapper for stage() api which gives the source
    # plugin a fully constructed path considering the
    # 'directory' option
    #
    def _stage(self, directory):
        self.validate_cache()
        if isinstance(directory, Directory):
            self.stage_directory(directory)
        else:
            self.stage(directory)

    # Wrapper for init_workspace()
    def _init_workspace(self, directory):
        if self.BST_STAGE_VIRTUAL_DIRECTORY:
            directory = FileBasedDirectory(external_directory=directory)

        self.validate_cache()
        if isinstance(directory, Directory):
            self.init_workspace_directory(directory)
        else:
            self.init_workspace(directory)

    # _get_unique_key():
    #
    # Wrapper for get_unique_key() api
    #
    def _get_unique_key(self):
        return self.get_unique_key()

    # _project_refs():
    #
    # Gets the appropriate ProjectRefs object for this source,
    # which depends on whether the owning element is a junction
    #
    # Args:
    #    project (Project): The project to check
    #
    def _project_refs(self, project):
        element_kind = self.__element_kind
        if element_kind == "junction":
            return project.junction_refs
        return project.refs

    # _load_ref():
    #
    # Loads the ref for the said source.
    #
    # Raises:
    #    (SourceError): If the source does not implement load_ref()
    #
    # Returns:
    #    (ref): A redundant ref specified inline for a project.refs using project
    #
    # This is partly a wrapper around `Source.load_ref()`, it will decide
    # where to load the ref from depending on which project the source belongs
    # to and whether that project uses a project.refs file.
    #
    # Note the return value is used to construct a summarized warning in the
    # case that the toplevel project uses project.refs and also lists refs
    # which will be ignored.
    #
    def _load_ref(self):
        context = self._get_context()
        project = self._get_project()
        toplevel = context.get_toplevel_project()
        redundant_ref = None

        element_name = self.__element_name
        element_idx = self.__element_index

        def do_load_ref(node):
            try:
                self.load_ref(ref_node)
            except ImplError as e:
                raise SourceError(
                    "{}: Storing refs in project.refs is not supported by '{}' sources".format(self, self.get_kind()),
                    reason="unsupported-load-ref",
                ) from e

        # If the main project overrides the ref, use the override
        if project is not toplevel and toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS:
            refs = self._project_refs(toplevel)
            ref_node = refs.lookup_ref(project.name, element_name, element_idx)
            if ref_node is not None:
                do_load_ref(ref_node)
                return redundant_ref

        # If the project itself uses project.refs, clear the ref which
        # was already loaded via Source.configure(), as this would
        # violate the rule of refs being either in project.refs or in
        # the elements themselves.
        #
        if project.ref_storage == ProjectRefStorage.PROJECT_REFS:

            # First warn if there is a ref already loaded, and reset it
            redundant_ref = self.get_ref()  # pylint: disable=assignment-from-no-return
            if redundant_ref is not None:
                self.set_ref(None, MappingNode.from_dict({}))

            # Try to load the ref
            refs = self._project_refs(project)
            ref_node = refs.lookup_ref(project.name, element_name, element_idx)
            if ref_node is not None:
                do_load_ref(ref_node)

        return redundant_ref

    # _set_ref()
    #
    # Persists the ref for this source. This will decide where to save the
    # ref, or refuse to persist it, depending on active ref-storage project
    # settings.
    #
    # Args:
    #    new_ref (smth): The new reference to save
    #    save (bool): Whether to write the new reference to file or not
    #
    # Returns:
    #    (bool): Whether the ref has changed
    #
    # Raises:
    #    (SourceError): In the case we encounter errors saving a file to disk
    #
    def _set_ref(self, new_ref, *, save):

        context = self._get_context()
        project = self._get_project()
        toplevel = context.get_toplevel_project()
        toplevel_refs = self._project_refs(toplevel)
        provenance = self._get_provenance()

        element_name = self.__element_name
        element_idx = self.__element_index

        #
        # Step 1 - Obtain the node
        #
        node = {}
        if toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS:
            node = toplevel_refs.lookup_ref(project.name, element_name, element_idx, write=True)

        if project is toplevel and not node:
            node = provenance._node

        #
        # Step 2 - Set the ref in memory, and determine changed state
        #
        clean = node.strip_node_info()

        # Set the ref regardless of whether it changed, the
        # TrackQueue() will want to update a specific node with
        # the ref, regardless of whether the original has changed.
        #
        # In the following add/del/mod merge algorithm we are working with
        # dictionaries, but the plugin API calls for a MappingNode.
        #
        modify = node.clone()
        self.set_ref(new_ref, modify)
        to_modify = modify.strip_node_info()

        # FIXME: this will save things too often, as a ref might not have
        #        changed. We should optimize this to detect it differently
        if not save:
            return False

        # Ensure the node is not from a junction
        if not toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS and provenance._project is not toplevel:
            if provenance._project is project:
                self.warn("{}: Not persisting new reference in junctioned project".format(self))
            elif provenance._project is None:
                assert provenance._filename == ""
                assert provenance._shortname == ""

                raise SourceError("{}: Error saving source reference to synthetic node.".format(self))
            else:
                raise SourceError(
                    "{}: Cannot track source in a fragment from a junction".format(provenance._shortname),
                    reason="tracking-junction-fragment",
                )

        actions = {}
        for k, v in clean.items():
            if k not in to_modify:
                actions[k] = "del"
            else:
                if v != to_modify[k]:
                    actions[k] = "mod"
        for k in to_modify.keys():
            if k not in clean:
                actions[k] = "add"

        def walk_container(container, path):
            # For each step along path, synthesise if we need to.
            # If we're synthesising missing list entries, we know we're
            # doing this for project.refs so synthesise empty dicts for the
            # intervening entries too
            lpath = path.copy()
            lpath.append("")  # We know the last step will be a string key
            for step, next_step in zip(lpath, lpath[1:]):
                if type(step) is str:  # pylint: disable=unidiomatic-typecheck
                    # handle dict container
                    if step not in container:
                        if type(next_step) is str:  # pylint: disable=unidiomatic-typecheck
                            container[step] = {}
                        else:
                            container[step] = []
                    container = container[step]
                else:
                    # handle list container
                    if len(container) <= step:
                        while len(container) <= step:
                            container.append({})
                    container = container[step]
            return container

        def process_value(action, container, path, key, new_value):
            container = walk_container(container, path)
            if action == "del":
                del container[key]
            elif action == "mod":
                container[key] = new_value
            elif action == "add":
                container[key] = new_value
            else:
                assert False, "BUG: Unknown action: {}".format(action)

        roundtrip_cache = {}
        for key, action in actions.items():
            # Obtain the top level node and its file
            if action == "add":
                provenance = node.get_provenance()
            else:
                provenance = node.get_node(key).get_provenance()

            toplevel_node = provenance._toplevel

            # Get the path to whatever changed
            if action == "add":
                path = toplevel_node._find(node)
            else:
                full_path = toplevel_node._find(node.get_node(key))
                # We want the path to the node containing the key, not to the key
                path = full_path[:-1]

            roundtrip_file = roundtrip_cache.get(provenance._filename)
            if not roundtrip_file:
                roundtrip_file = roundtrip_cache[provenance._filename] = _yaml.roundtrip_load(
                    provenance._filename, allow_missing=True
                )

            # Get the value of the round trip file that we need to change
            process_value(action, roundtrip_file, path, key, to_modify.get(key))

        #
        # Step 3 - Apply the change in project data
        #
        for filename, data in roundtrip_cache.items():
            # This is our roundtrip dump from the track
            try:
                _yaml.roundtrip_dump(data, filename)
            except OSError as e:
                raise SourceError(
                    "{}: Error saving source reference to '{}': {}".format(self, filename, e), reason="save-ref-error"
                ) from e

        return True

    # Wrapper for track()
    #
    # Args:
    #   previous_sources_dir (str): directory where previous sources are staged
    #
    def _track(self, previous_sources_dir: str = None) -> SourceRef:
        if self.BST_REQUIRES_PREVIOUS_SOURCES_TRACK:
            new_ref = self.__do_track(previous_sources_dir=previous_sources_dir)
        else:
            new_ref = self.__do_track()

        current_ref = self.get_ref()  # pylint: disable=assignment-from-no-return

        if new_ref is None:
            # No tracking, keep current ref
            new_ref = current_ref

        if current_ref != new_ref:
            self.info("Found new revision: {}".format(new_ref))

            # Save ref in local process for subsequent sources
            self._set_ref(new_ref, save=False)

        self._generate_key()

        return new_ref

    # _requires_previous_sources()
    #
    # If a plugin requires access to previous sources at track or fetch time,
    # then it cannot be the first source of an elemenet.
    #
    # Returns:
    #   (bool): Whether this source requires access to previous sources
    #
    def _requires_previous_sources(self):
        return self.BST_REQUIRES_PREVIOUS_SOURCES_TRACK or self.BST_REQUIRES_PREVIOUS_SOURCES_FETCH

    # Returns the alias if it's defined in the project
    def _get_alias(self):
        alias = self.__expected_alias
        project = self._get_project()
        if project.alias_exists(alias, first_pass=self.__first_pass):
            # The alias must already be defined in the project's aliases
            # otherwise http://foo gets treated like it contains an alias
            return alias
        else:
            return None

    def _generate_key(self):
        self.__key = generate_key(self._get_unique_key())

    @property
    def _key(self):
        return self.__key

    # Gives a ref path that points to where sources are kept in the CAS
    def _get_source_name(self):
        # @ is used to prevent conflicts with project names
        return "{}/{}".format(self.get_kind(), self._key)

    def _get_brief_display_key(self):
        context = self._get_context()
        key = self._key

        length = min(len(key), context.log_key_length)
        return key[:length]

    @property
    def _element_name(self):
        return self.__element_name

    # _cache_directory()
    #
    # A context manager to cache and retrieve content.
    #
    # If the digest is not specified, then a new directory is prepared, the
    # content of which can later be addressed by accessing it's digest,
    # using the private API Directory._get_digest().
    #
    # The hash of the Digest of the cached directory is suitable for use as a
    # cache key, and the Digest object can be reused later on to do the
    # staging operation.
    #
    # This context manager was added specifically to optimize cases where
    # we have project or host local data to stage into CAS, such as local
    # sources and workspaces.
    #
    # Args:
    #    digest: A Digest of previously cached content.
    #
    # Yields:
    #    (Directory): A handle on the cached content directory
    #
    @contextmanager
    def _cache_directory(self, digest=None):
        context = self._get_context()
        cache = context.get_cascache()
        cas_dir = CasBasedDirectory(cache, digest=digest)

        yield cas_dir

    #############################################################
    #                   Local Private Methods                   #
    #############################################################

    # __clone_for_uri()
    #
    # Clone the source with an alternative URI setup for the alias
    # which this source uses.
    #
    # This is used for iteration over source mirrors.
    #
    # Args:
    #    uri (str): The alternative URI for this source's alias
    #
    # Returns:
    #    (Source): A new clone of this Source, with the specified URI
    #              as the value of the alias this Source has marked as
    #              primary with either mark_download_url() or
    #              translate_url().
    #
    def __clone_for_uri(self, uri):
        project = self._get_project()
        context = self._get_context()
        alias = self._get_alias()
        source_kind = type(self)

        # Rebuild a MetaSource from the current element
        meta = MetaSource(
            self.__element_name,
            self.__element_index,
            self.__element_kind,
            self.get_kind(),
            self.__config,
            self._directory,
            self.__first_pass,
        )

        clone = source_kind(
            context, project, meta, self.__variables, alias_override=(alias, uri), unique_id=self._unique_id
        )

        # Do the necessary post instantiation routines here
        #
        clone._preflight()
        clone._load_ref()

        return clone

    # Tries to call fetch for every mirror, stopping once it succeeds
    def __do_fetch(self, **kwargs):
        project = self._get_project()
        context = self._get_context()

        # Silence the STATUS messages which might happen as a result
        # of checking the source fetchers.
        with context.messenger.silence():
            source_fetchers = self.get_source_fetchers()

        # Use the source fetchers if they are provided
        #
        if source_fetchers:

            # Use a contorted loop here, this is to allow us to
            # silence the messages which can result from consuming
            # the items of source_fetchers, if it happens to be a generator.
            #
            source_fetchers = iter(source_fetchers)

            while True:

                with context.messenger.silence():
                    try:
                        fetcher = next(source_fetchers)
                    except StopIteration:
                        # as per PEP479, we are not allowed to let StopIteration
                        # thrown from a context manager.
                        # Catching it here and breaking instead.
                        break

                alias = fetcher._get_alias()
                last_error = None
                for uri in project.get_alias_uris(alias, first_pass=self.__first_pass, tracking=False):
                    try:
                        fetcher.fetch(uri)
                    # FIXME: Need to consider temporary vs. permanent failures,
                    #        and how this works with retries.
                    except BstError as e:
                        last_error = e
                        continue

                    # No error, we're done with this fetcher
                    break

                else:
                    # No break occurred, raise the last detected error
                    raise last_error

        # Default codepath is to reinstantiate the Source
        #
        else:
            alias = self._get_alias()
            if self.__first_pass:
                mirrors = project.first_pass_config.mirrors
            else:
                mirrors = project.config.mirrors
            if not mirrors or not alias:
                self.fetch(**kwargs)
                return

            for uri in project.get_alias_uris(alias, first_pass=self.__first_pass, tracking=False):
                new_source = self.__clone_for_uri(uri)
                try:
                    new_source.fetch(**kwargs)
                # FIXME: Need to consider temporary vs. permanent failures,
                #        and how this works with retries.
                except BstError as e:
                    last_error = e
                    continue

                # No error, we're done here
                return

            # Re raise the last detected error
            raise last_error

    # Tries to call track for every mirror, stopping once it succeeds
    def __do_track(self, **kwargs):
        project = self._get_project()
        alias = self._get_alias()
        if self.__first_pass:
            mirrors = project.first_pass_config.mirrors
        else:
            mirrors = project.config.mirrors
        # If there are no mirrors, or no aliases to replace, there's nothing to do here.
        if not mirrors or not alias:
            return self.track(**kwargs)

        # NOTE: We are assuming here that tracking only requires substituting the
        #       first alias used
        last_error = None
        for uri in reversed(project.get_alias_uris(alias, first_pass=self.__first_pass, tracking=True)):
            new_source = self.__clone_for_uri(uri)
            try:
                ref = new_source.track(**kwargs)  # pylint: disable=assignment-from-none
            # FIXME: Need to consider temporary vs. permanent failures,
            #        and how this works with retries.
            except BstError as e:
                last_error = e
                continue
            return ref
        raise last_error

    @classmethod
    def __init_defaults(cls, project, meta):
        if cls.__defaults is None:
            if meta.first_pass:
                sources = project.first_pass_config.source_overrides
            else:
                sources = project.source_overrides
            cls.__defaults = sources.get_mapping(meta.kind, default={})

    # This will resolve the final configuration to be handed
    # off to source.configure()
    #
    @classmethod
    def __extract_config(cls, meta):
        config = cls.__defaults.get_mapping("config", default={})
        config = config.clone()

        meta.config._composite(config)
        config._assert_fully_composited()

        return config


def _extract_alias(url):
    parts = url.split(utils._ALIAS_SEPARATOR, 1)
    if len(parts) > 1 and not parts[0].lower() in utils._URI_SCHEMES:
        return parts[0]
    else:
        return ""
