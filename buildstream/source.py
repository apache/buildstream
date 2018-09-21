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
"""
Source - Base source class
==========================


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

* :func:`Source.get_consistency() <buildstream.source.Source.get_consistency>`

  Report the sources consistency state.

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

* :func:`Source.stage() <buildstream.source.Source.stage>`

  Stage the sources for a given ref at a specified location

* :func:`Source.init_workspace() <buildstream.source.Source.init_workspace>`

  Stage sources in a local directory for use as a workspace.

  **Optional**: If left unimplemented, this will default to calling
  :func:`Source.stage() <buildstream.source.Source.stage>`

* :func:`Source.get_source_fetchers() <buildstream.source.Source.get_source_fetchers>`

  Get the objects that are used for fetching.

  **Optional**: This only needs to be implemented for sources that need to
  download from multiple URLs while fetching (e.g. a git repo and its
  submodules). For details on how to define a SourceFetcher, see
  :ref:`SourceFetcher <core_source_fetcher>`.


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

"""

import os
from collections import Mapping
from contextlib import contextmanager

from . import Plugin
from . import _yaml, utils
from ._exceptions import BstError, ImplError, ErrorDomain
from ._projectrefs import ProjectRefStorage


class Consistency():
    INCONSISTENT = 0
    """Inconsistent

    Inconsistent sources have no explicit reference set. They cannot
    produce a cache key, be fetched or staged. They can only be tracked.
    """

    RESOLVED = 1
    """Resolved

    Resolved sources have a reference and can produce a cache key and
    be fetched, however they cannot be staged.
    """

    CACHED = 2
    """Cached

    Cached sources have a reference which is present in the local
    source cache. Only cached sources can be staged.
    """


class SourceError(BstError):
    """This exception should be raised by :class:`.Source` implementations
    to report errors to the user.

    Args:
       message (str): The breif error description to report to the user
       detail (str): A possibly multiline, more detailed error message
       reason (str): An optional machine readable reason string, used for test cases
       temporary (bool): An indicator to whether the error may occur if the operation was run again.  (*Since: 1.2*)
    """
    def __init__(self, message, *, detail=None, reason=None, temporary=False):
        super().__init__(message, detail=detail, domain=ErrorDomain.SOURCE, reason=reason, temporary=temporary)


class SourceFetcher():
    """SourceFetcher()

    This interface exists so that a source that downloads from multiple
    places (e.g. a git source with submodules) has a consistent interface for
    fetching and substituting aliases.

    *Since: 1.2*

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
    def fetch(self, alias_override=None):
        """Fetch remote sources and mirror them locally, ensuring at least
        that the specific reference is cached locally.

        Args:
           alias_override (str): The alias to use instead of the default one
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
    def mark_download_url(self, url):
        """Identifies the URL that this SourceFetcher uses to download

        This must be called during the fetcher's initialization

        Args:
           url (str): The url used to download.
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
    __defaults = {}          # The defaults from the project
    __defaults_set = False   # Flag, in case there are not defaults at all

    def __init__(self, context, project, meta, *, alias_override=None):
        provenance = _yaml.node_get_provenance(meta.config)
        super().__init__("{}-{}".format(meta.element_name, meta.element_index),
                         context, project, provenance, "source")

        self.__element_name = meta.element_name         # The name of the element owning this source
        self.__element_index = meta.element_index       # The index of the source in the owning element's source list
        self.__element_kind = meta.element_kind         # The kind of the element owning this source
        self.__directory = meta.directory               # Staging relative directory
        self.__consistency = Consistency.INCONSISTENT   # Cached consistency state

        # The alias_override is only set on a re-instantiated Source
        self.__alias_override = alias_override          # Tuple of alias and its override to use instead
        self.__expected_alias = None                    # The primary alias
        self.__marked_urls = set()                      # Set of marked download URLs

        # FIXME: Reconstruct a MetaSource from a Source instead of storing it.
        self.__meta = meta                              # MetaSource stored so we can copy this source later.

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__init_defaults(meta)
        self.__config = self.__extract_config(meta)
        self.__first_pass = meta.first_pass

        self._configure(self.__config)

    COMMON_CONFIG_KEYS = ['kind', 'directory']
    """Common source config keys

    Source config keys that must not be accessed in configure(), and
    should be checked for using node_validate().
    """

    #############################################################
    #                      Abstract Methods                     #
    #############################################################
    def get_consistency(self):
        """Report whether the source has a resolved reference

        Returns:
           (:class:`.Consistency`): The source consistency
        """
        raise ImplError("Source plugin '{}' does not implement get_consistency()".format(self.get_kind()))

    def load_ref(self, node):
        """Loads the *ref* for this Source from the specified *node*.

        Args:
           node (dict): The YAML node to load the ref from

        .. note::

           The *ref* for the Source is expected to be read at
           :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` time,
           this will only be used for loading refs from alternative locations
           than in the `element.bst` file where the given Source object has
           been declared.

        *Since: 1.2*
        """
        raise ImplError("Source plugin '{}' does not implement load_ref()".format(self.get_kind()))

    def get_ref(self):
        """Fetch the internal ref, however it is represented

        Returns:
           (simple object): The internal source reference, or ``None``

        .. note::

           The reference is the user provided (or track resolved) value
           the plugin uses to represent a specific input, like a commit
           in a VCS or a tarball's checksum. Usually the reference is a string,
           but the plugin may choose to represent it with a tuple or such.

           Implementations *must* return a ``None`` value in the case that
           the ref was not loaded. E.g. a ``(None, None)`` tuple is not acceptable.
        """
        raise ImplError("Source plugin '{}' does not implement get_ref()".format(self.get_kind()))

    def set_ref(self, ref, node):
        """Applies the internal ref, however it is represented

        Args:
           ref (simple object): The internal source reference to set, or ``None``
           node (dict): The same dictionary which was previously passed
                        to :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>`

        See :func:`Source.get_ref() <buildstream.source.Source.get_ref>`
        for a discussion on the *ref* parameter.

        .. note::

           Implementors must support the special ``None`` value here to
           allow clearing any existing ref.
        """
        raise ImplError("Source plugin '{}' does not implement set_ref()".format(self.get_kind()))

    def track(self):
        """Resolve a new ref from the plugin's track option

        Returns:
           (simple object): A new internal source reference, or None

        If the backend in question supports resolving references from
        a symbolic tracking branch or tag, then this should be implemented
        to perform this task on behalf of ``build-stream track`` commands.

        This usually requires fetching new content from a remote origin
        to see if a new ref has appeared for your branch or tag. If the
        backend store allows one to query for a new ref from a symbolic
        tracking data without downloading then that is desirable.

        See :func:`Source.get_ref() <buildstream.source.Source.get_ref>`
        for a discussion on the *ref* parameter.
        """
        # Allow a non implementation
        return None

    def fetch(self):
        """Fetch remote sources and mirror them locally, ensuring at least
        that the specific reference is cached locally.

        Raises:
           :class:`.SourceError`

        Implementors should raise :class:`.SourceError` if the there is some
        network error or if the source reference could not be matched.
        """
        raise ImplError("Source plugin '{}' does not implement fetch()".format(self.get_kind()))

    def stage(self, directory):
        """Stage the sources to a directory

        Args:
           directory (str): Path to stage the source

        Raises:
           :class:`.SourceError`

        Implementors should assume that *directory* already exists
        and stage already cached sources to the passed directory.

        Implementors should raise :class:`.SourceError` when encountering
        some system error.
        """
        raise ImplError("Source plugin '{}' does not implement stage()".format(self.get_kind()))

    def init_workspace(self, directory):
        """Initialises a new workspace

        Args:
           directory (str): Path of the workspace to init

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

    def get_source_fetchers(self):
        """Get the objects that are used for fetching

        If this source doesn't download from multiple URLs,
        returning None and falling back on the default behaviour
        is recommended.

        Returns:
           iterable: The Source's SourceFetchers, if any.

        .. note::

           Implementors can implement this as a generator.

           The :func:`SourceFetcher.fetch() <buildstream.source.SourceFetcher.fetch>`
           method will be called on the returned fetchers one by one,
           before consuming the next fetcher in the list.

        *Since: 1.2*
        """

        return []

    #############################################################
    #                       Public Methods                      #
    #############################################################
    def get_mirror_directory(self):
        """Fetches the directory where this source should store things

        Returns:
           (str): The directory belonging to this source
        """

        # Create the directory if it doesnt exist
        context = self._get_context()
        directory = os.path.join(context.sourcedir, self.get_kind())
        os.makedirs(directory, exist_ok=True)
        return directory

    def translate_url(self, url, *, alias_override=None, primary=True):
        """Translates the given url which may be specified with an alias
        into a fully qualified url.

        Args:
           url (str): A URL, which may be using an alias
           alias_override (str): Optionally, an URI to override the alias with. (*Since: 1.2*)
           primary (bool): Whether this is the primary URL for the source. (*Since: 1.2*)

        Returns:
           str: The fully qualified URL, with aliases resolved
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
                    override_alias = self.__alias_override[0]
                    override_url = self.__alias_override[1]
                    if url_alias == override_alias:
                        url = override_url + url_body
            return url
        else:
            project = self._get_project()
            return project.translate_url(url, first_pass=self.__first_pass)

    def mark_download_url(self, url, *, primary=True):
        """Identifies the URL that this Source uses to download

        Args:
           url (str): The URL used to download
           primary (bool): Whether this is the primary URL for the source

        .. note::

           This must be called for every URL in the configuration during
           :func:`Plugin.configure() <buildstream.plugin.Plugin.configure>` if
           :func:`Source.translate_url() <buildstream.source.Source.translate_url>`
           is not called.

        *Since: 1.2*
        """
        # Only mark the Source level aliases on the main instance, not in
        # a reinstantiated instance in mirroring.
        if not self.__alias_override:
            if primary:
                expected_alias = _extract_alias(url)

                assert (self.__expected_alias is None or
                        self.__expected_alias == expected_alias), \
                    "Primary URL marked twice with different URLs"

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
            assert (url in self.__marked_urls or not _extract_alias(url)), \
                "URL was not seen at configure time: {}".format(url)

    def get_project_directory(self):
        """Fetch the project base directory

        This is useful for sources which need to load resources
        stored somewhere inside the project.

        Returns:
           str: The project base directory
        """
        project = self._get_project()
        return project.directory

    @contextmanager
    def tempdir(self):
        """Context manager for working in a temporary directory

        Yields:
           (str): A path to a temporary directory

        This should be used by source plugins directly instead of the tempfile
        module. This one will automatically cleanup in case of termination by
        catching the signal before os._exit(). It will also use the 'mirror
        directory' as expected for a source.
        """
        mirrordir = self.get_mirror_directory()
        with utils._tempdir(dir=mirrordir) as tempdir:
            yield tempdir

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

    # Update cached consistency for a source
    #
    # This must be called whenever the state of a source may have changed.
    #
    def _update_state(self):

        if self.__consistency < Consistency.CACHED:

            # Source consistency interrogations are silent.
            context = self._get_context()
            with context.silence():
                self.__consistency = self.get_consistency()

    # Return cached consistency
    #
    def _get_consistency(self):
        return self.__consistency

    # Wrapper function around plugin provided fetch method
    #
    def _fetch(self):
        project = self._get_project()
        source_fetchers = self.get_source_fetchers()

        # Use the source fetchers if they are provided
        #
        if source_fetchers:
            for fetcher in source_fetchers:
                alias = fetcher._get_alias()
                for uri in project.get_alias_uris(alias, first_pass=self.__first_pass):
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
                self.fetch()
                return

            for uri in project.get_alias_uris(alias, first_pass=self.__first_pass):
                new_source = self.__clone_for_uri(uri)
                try:
                    new_source.fetch()
                # FIXME: Need to consider temporary vs. permanent failures,
                #        and how this works with retries.
                except BstError as e:
                    last_error = e
                    continue

                # No error, we're done here
                return

            # Re raise the last detected error
            raise last_error

    # Wrapper for stage() api which gives the source
    # plugin a fully constructed path considering the
    # 'directory' option
    #
    def _stage(self, directory):
        staging_directory = self.__ensure_directory(directory)

        self.stage(staging_directory)

    # Wrapper for init_workspace()
    def _init_workspace(self, directory):
        directory = self.__ensure_directory(directory)

        self.init_workspace(directory)

    # _get_unique_key():
    #
    # Wrapper for get_unique_key() api
    #
    # Args:
    #    include_source (bool): Whether to include the delegated source key
    #
    def _get_unique_key(self, include_source):
        key = {}

        key['directory'] = self.__directory
        if include_source:
            key['unique'] = self.get_unique_key()

        return key

    # Wrapper for set_ref(), also returns whether it changed.
    #
    def _set_ref(self, ref, node):
        current_ref = self.get_ref()
        changed = False

        # This comparison should work even for tuples and lists,
        # but we're mostly concerned about simple strings anyway.
        if current_ref != ref:
            changed = True

        # Set the ref regardless of whether it changed, the
        # TrackQueue() will want to update a specific node with
        # the ref, regardless of whether the original has changed.
        self.set_ref(ref, node)

        return changed

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
        if element_kind == 'junction':
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
                raise SourceError("{}: Storing refs in project.refs is not supported by '{}' sources"
                                  .format(self, self.get_kind()),
                                  reason="unsupported-load-ref") from e

        # If the main project overrides the ref, use the override
        if project is not toplevel and toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS:
            refs = self._project_refs(toplevel)
            ref_node = refs.lookup_ref(project.name, element_name, element_idx)
            if ref_node is not None:
                do_load_ref(ref_node)

        # If the project itself uses project.refs, clear the ref which
        # was already loaded via Source.configure(), as this would
        # violate the rule of refs being either in project.refs or in
        # the elements themselves.
        #
        elif project.ref_storage == ProjectRefStorage.PROJECT_REFS:

            # First warn if there is a ref already loaded, and reset it
            redundant_ref = self.get_ref()
            if redundant_ref is not None:
                self.set_ref(None, {})

            # Try to load the ref
            refs = self._project_refs(project)
            ref_node = refs.lookup_ref(project.name, element_name, element_idx)
            if ref_node is not None:
                do_load_ref(ref_node)

        return redundant_ref

    # _save_ref()
    #
    # Persists the ref for this source. This will decide where to save the
    # ref, or refuse to persist it, depending on active ref-storage project
    # settings.
    #
    # Args:
    #    new_ref (smth): The new reference to save
    #
    # Returns:
    #    (bool): Whether the ref has changed
    #
    # Raises:
    #    (SourceError): In the case we encounter errors saving a file to disk
    #
    def _save_ref(self, new_ref):

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
        if project is toplevel:
            if toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS:
                node = toplevel_refs.lookup_ref(project.name, element_name, element_idx, write=True)
            else:
                node = provenance.node
        else:
            if toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS:
                node = toplevel_refs.lookup_ref(project.name, element_name, element_idx, write=True)
            else:
                node = {}

        #
        # Step 2 - Set the ref in memory, and determine changed state
        #
        if not self._set_ref(new_ref, node):
            return False

        def do_save_refs(refs):
            try:
                refs.save()
            except OSError as e:
                raise SourceError("{}: Error saving source reference to 'project.refs': {}"
                                  .format(self, e),
                                  reason="save-ref-error") from e

        #
        # Step 3 - Apply the change in project data
        #
        if toplevel.ref_storage == ProjectRefStorage.PROJECT_REFS:
            do_save_refs(toplevel_refs)
        else:
            if provenance.filename.project is toplevel:
                # Save the ref in the originating file
                #
                try:
                    _yaml.dump(provenance.toplevel, provenance.filename.name)
                except OSError as e:
                    raise SourceError("{}: Error saving source reference to '{}': {}"
                                      .format(self, provenance.filename.name, e),
                                      reason="save-ref-error") from e
            elif provenance.filename.project is project:
                self.warn("{}: Not persisting new reference in junctioned project".format(self))
            elif provenance.filename.project is None:
                assert provenance.filename.name == ''
                assert provenance.filename.shortname == ''
                raise SourceError("{}: Error saving source reference to synthetic node."
                                  .format(self))
            else:
                raise SourceError("{}: Cannot track source in a fragment from a junction"
                                  .format(provenance.filename.shortname),
                                  reason="tracking-junction-fragment")

        return True

    # Wrapper for track()
    #
    def _track(self):
        new_ref = self.__do_track()
        current_ref = self.get_ref()

        if new_ref is None:
            # No tracking, keep current ref
            new_ref = current_ref

        if current_ref != new_ref:
            self.info("Found new revision: {}".format(new_ref))

        return new_ref

    # Returns the alias if it's defined in the project
    def _get_alias(self):
        alias = self.__expected_alias
        project = self._get_project()
        if project.get_alias_uri(alias, first_pass=self.__first_pass):
            # The alias must already be defined in the project's aliases
            # otherwise http://foo gets treated like it contains an alias
            return alias
        else:
            return None

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

        clone = source_kind(context, project, self.__meta, alias_override=(alias, uri))

        # Do the necessary post instantiation routines here
        #
        clone._preflight()
        clone._load_ref()
        clone._update_state()

        return clone

    # Tries to call track for every mirror, stopping once it succeeds
    def __do_track(self):
        project = self._get_project()
        alias = self._get_alias()
        if self.__first_pass:
            mirrors = project.first_pass_config.mirrors
        else:
            mirrors = project.config.mirrors
        # If there are no mirrors, or no aliases to replace, there's nothing to do here.
        if not mirrors or not alias:
            return self.track()

        # NOTE: We are assuming here that tracking only requires substituting the
        #       first alias used
        for uri in reversed(project.get_alias_uris(alias, first_pass=self.__first_pass)):
            new_source = self.__clone_for_uri(uri)
            try:
                ref = new_source.track()
            # FIXME: Need to consider temporary vs. permanent failures,
            #        and how this works with retries.
            except BstError as e:
                last_error = e
                continue
            return ref
        raise last_error

    # Ensures a fully constructed path and returns it
    def __ensure_directory(self, directory):

        if self.__directory is not None:
            directory = os.path.join(directory, self.__directory.lstrip(os.sep))

        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise SourceError("Failed to create staging directory: {}"
                              .format(e),
                              reason="ensure-stage-dir-fail") from e
        return directory

    def __init_defaults(self, meta):
        if not self.__defaults_set:
            project = self._get_project()
            if meta.first_pass:
                sources = project.first_pass_config.source_overrides
            else:
                sources = project.source_overrides
            type(self).__defaults = sources.get(self.get_kind(), {})
            type(self).__defaults_set = True

    # This will resolve the final configuration to be handed
    # off to source.configure()
    #
    def __extract_config(self, meta):
        config = _yaml.node_get(self.__defaults, Mapping, 'config', default_value={})
        config = _yaml.node_chain_copy(config)

        _yaml.composite(config, meta.config)
        _yaml.node_final_assertions(config)

        return config


def _extract_alias(url):
    parts = url.split(utils._ALIAS_SEPARATOR, 1)
    if len(parts) > 1 and not parts[0].lower() in utils._URI_SCHEMES:
        return parts[0]
    else:
        return ""
