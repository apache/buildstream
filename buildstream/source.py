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
    """
    def __init__(self, message, *, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.SOURCE, reason=reason)


class Source(Plugin):
    """Source()

    Base Source class.

    All Sources derive from this class, this interface defines how
    the core will be interacting with Sources.
    """
    __defaults = {}          # The defaults from the project
    __defaults_set = False   # Flag, in case there are not defaults at all

    def __init__(self, context, project, meta):
        provenance = _yaml.node_get_provenance(meta.config)
        super().__init__("{}-{}".format(meta.element_name, meta.element_index),
                         context, project, provenance, "source")

        self.__element_name = meta.element_name         # The name of the element owning this source
        self.__element_index = meta.element_index       # The index of the source in the owning element's source list
        self.__element_kind = meta.element_kind         # The kind of the element owning this source
        self.__directory = meta.directory               # Staging relative directory
        self.__consistency = Consistency.INCONSISTENT   # Cached consistency state

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__init_defaults(meta)
        self.__config = self.__extract_config(meta)

        self.configure(self.__config)

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
                        to :func:`~buildstream.source.Source.configure`

        See :func:`~buildstream.source.Source.get_ref` for a discussion on
        the *ref* parameter.

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

        See :func:`~buildstream.source.Source.get_ref` for a discussion on
        the *ref* parameter.
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
        :func:`~buildstream.source.Source.stage`.

        Implementors overriding this method should assume that *directory*
        already exists.

        Implementors should raise :class:`.SourceError` when encountering
        some system error.
        """
        self.stage(directory)

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

    def translate_url(self, url):
        """Translates the given url which may be specified with an alias
        into a fully qualified url.

        Args:
           url (str): A url, which may be using an alias

        Returns:
           str: The fully qualified url, with aliases resolved
        """
        project = self._get_project()
        return project.translate_url(url)

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
        self.fetch()

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
        assert provenance.filename.project is not None

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
        changed = self._set_ref(new_ref, node)

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
                    _yaml.dump(_yaml.node_sanitize(provenance.toplevel), provenance.filename.name)
                except OSError as e:
                    raise SourceError("{}: Error saving source reference to '{}': {}"
                                      .format(self, provenance.filename.name, e),
                                      reason="save-ref-error") from e
            elif provenance.filename.project is project:
                self.warn("{}: Not persisting new reference in junctioned project".format(self))
            else:
                raise SourceError("{}: Cannot track source in a fragment from a junction"
                                  .format(provenance.filename.shortname),
                                  reason="tracking-junction-fragment")

        return changed

    # Wrapper for track()
    #
    def _track(self):
        new_ref = self.track()
        current_ref = self.get_ref()

        if new_ref is None:
            # No tracking, keep current ref
            new_ref = current_ref

        if current_ref != new_ref:
            self.info("Found new revision: {}".format(new_ref))

        return new_ref

    #############################################################
    #                   Local Private Methods                   #
    #############################################################

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
