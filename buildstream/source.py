#!/usr/bin/env python3
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
Source
======
"""

import os
from collections import Mapping
from contextlib import contextmanager

from . import Plugin
from . import _yaml, utils
from ._exceptions import BstError, ImplError, LoadError, LoadErrorReason, ErrorDomain
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
        self.__directory = meta.directory               # Staging relative directory
        self.__origin_node = meta.origin_node           # YAML node this Source was loaded from
        self.__origin_toplevel = meta.origin_toplevel   # Toplevel YAML node for the file
        self.__origin_filename = meta.origin_filename   # Filename of the file the source was loaded from
        self.__consistency = Consistency.INCONSISTENT   # Cached consistency state
        self.__tracking = False                         # Source is scheduled to be tracked
        self.__assemble_scheduled = False               # Source is scheduled to be assembled
        self.__workspace = None                         # Directory of the currently active workspace
        self.__workspace_key = None                     # Cached directory content hashes for workspaced source

        # Collect the composited element configuration and
        # ask the element to configure itself.
        self.__init_defaults()
        self.__config = self.__extract_config(meta)
        self.configure(self.__config)

    COMMON_CONFIG_KEYS = ['kind', 'directory']
    """Common source config keys

    Source config keys that must not be accessed in configure(), and
    should be checked for using node_validate().
    """

    def __init_defaults(self):
        if not self.__defaults_set:
            project = self._get_project()
            sources = project._sources
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
    #            Private Methods used in BuildStream            #
    #############################################################

    # Update cached consistency for a source
    #
    # This must be called whenever the state of a source may have changed.
    #
    def _update_state(self):
        if self.__tracking:
            return

        if self.__consistency < Consistency.CACHED:

            # Source consistency interrogations are silent.
            context = self._get_context()
            with context._silence():
                self.__consistency = self.get_consistency()

            if self._has_workspace() and \
               self.__consistency > Consistency.INCONSISTENT:

                # A workspace is considered inconsistent in the case
                # that it's directory went missing
                #
                fullpath = self._get_workspace_path()
                if not os.path.exists(fullpath):
                    self.__consistency = Consistency.INCONSISTENT

    # Return cached consistency
    #
    def _get_consistency(self):
        return self.__consistency

    # Return the absolute path of the element's workspace
    #
    def _get_workspace_path(self):
        return os.path.join(self.get_project_directory(), self.__workspace)

    # Mark a source as scheduled to be tracked
    #
    # This is used across the pipeline in sessions where the
    # source in question are going to be tracked. This is important
    # as it will prevent depending elements from producing cache
    # keys until the source is RESOLVED and also prevent depending
    # elements from being assembled until the source is CACHED.
    #
    def _schedule_tracking(self):
        self.__tracking = True

    # _schedule_assemble():
    #
    # This is called in the main process before the element is assembled
    # in a subprocess.
    #
    def _schedule_assemble(self):
        assert not self.__assemble_scheduled
        self.__assemble_scheduled = True

        # Invalidate workspace key as the build modifies the workspace directory
        self.__workspace_key = None

    # _assemble_done():
    #
    # This is called in the main process after the element has been assembled
    # in a subprocess.
    #
    def _assemble_done(self):
        assert self.__assemble_scheduled
        self.__assemble_scheduled = False

    # _stable():
    #
    # Unstable sources are mounted read/write and thus cannot produce a
    # (stable) cache key before the build is complete.
    #
    def _stable(self):
        # Source directory is modified by workspace build process
        return not (self._has_workspace() and self.__assemble_scheduled)

    # Wrapper function around plugin provided fetch method
    #
    def _fetch(self):
        self.fetch()

    # Return the path where this source should be staged under given directory
    def _get_staging_path(self, directory):
        if self.__directory is not None:
            directory = os.path.join(directory, self.__directory.lstrip(os.sep))
        return directory

    # Ensures a fully constructed path and returns it
    def _ensure_directory(self, directory):
        directory = self._get_staging_path(directory)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise SourceError("Failed to create staging directory: {}"
                              .format(e),
                              reason="ensure-stage-dir-fail") from e
        return directory

    # Wrapper for stage() api which gives the source
    # plugin a fully constructed path considering the
    # 'directory' option
    #
    def _stage(self, directory):
        staging_directory = self._ensure_directory(directory)

        if self._has_workspace():
            self._stage_workspace(staging_directory)
        else:
            self.stage(staging_directory)

    # Wrapper for init_workspace()
    def _init_workspace(self, directory):
        directory = self._ensure_directory(directory)

        self.init_workspace(directory)

    # Wrapper for get_unique_key() api
    #
    # This adds any core attributes to the key and
    # also calculates something different if workspaces
    # are active.
    #
    def _get_unique_key(self):
        key = {}

        key['directory'] = self.__directory
        if self._has_workspace():
            key['workspace'] = self._get_workspace_key()
        else:
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

        self.__tracking = False

        return changed

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
        toplevel = context._get_toplevel_project()
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
        if project is not toplevel and toplevel._ref_storage == ProjectRefStorage.PROJECT_REFS:
            ref_node = toplevel.refs.lookup_ref(project.name, element_name, element_idx)
            if ref_node is not None:
                do_load_ref(ref_node)

        # If the project itself uses project.refs, clear the ref which
        # was already loaded via Source.configure(), as this would
        # violate the rule of refs being either in project.refs or in
        # the elements themselves.
        #
        elif project._ref_storage == ProjectRefStorage.PROJECT_REFS:

            # First warn if there is a ref already loaded, and reset it
            redundant_ref = self.get_ref()
            if redundant_ref is not None:
                self.set_ref(None, {})

            # Try to load the ref
            ref_node = project.refs.lookup_ref(project.name, element_name, element_idx)
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
    # Raises:
    #    (SourceError): In the case we encounter errors saving a file to disk
    #
    def _save_ref(self, new_ref):

        context = self._get_context()
        project = self._get_project()
        toplevel = context._get_toplevel_project()

        element_name = self.__element_name
        element_idx = self.__element_index

        #
        # Step 1 - Obtain the node
        #
        if project is toplevel:
            if toplevel._ref_storage == ProjectRefStorage.PROJECT_REFS:
                node = toplevel.refs.lookup_ref(project.name, element_name, element_idx, write=True)
            else:
                node = self.__origin_node
        else:
            if toplevel._ref_storage == ProjectRefStorage.PROJECT_REFS:
                node = toplevel.refs.lookup_ref(project.name, element_name, element_idx, write=True)
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
        if project is toplevel:
            if toplevel._ref_storage == ProjectRefStorage.PROJECT_REFS:
                do_save_refs(toplevel.refs)
            else:
                # Save the ref in the originating file
                #
                toplevel_node = self.__origin_toplevel
                filename = self.__origin_filename
                fullname = os.path.join(toplevel.element_path, filename)
                try:
                    _yaml.dump(toplevel_node, fullname)
                except OSError as e:
                    raise SourceError("{}: Error saving source reference to '{}': {}"
                                      .format(self, filename, e),
                                      reason="save-ref-error") from e
        else:
            if toplevel._ref_storage == ProjectRefStorage.PROJECT_REFS:
                do_save_refs(toplevel.refs)
            else:
                self.warn("{}: Not persisting new reference in junctioned project".format(self))

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
            if self._has_workspace():
                detail = "This source has an open workspace.\n" \
                    + "To start using the new reference, please close the existing workspace."
                self.warn("Updated reference will be ignored as source has open workspace", detail=detail)

        return new_ref

    # Set the current workspace directory
    #
    # Note that this invalidate the workspace key.
    #
    def _set_workspace(self, directory):
        self.__workspace = directory
        self.__workspace_key = None

    # Return the current workspace directory
    def _get_workspace(self):
        return self.__workspace

    # Delete the workspace
    #
    # Note that this invalidate the workspace key.
    #
    def _del_workspace(self):
        self.__workspace = None
        self.__workspace_key = None

    # Whether the source has a set workspace
    #
    def _has_workspace(self):
        return self.__workspace is not None

    # Stage the workspace
    #
    def _stage_workspace(self, directory):
        fullpath = self._get_workspace_path()

        with self.timed_activity("Staging local files at {}".format(self.__workspace)):
            if os.path.isdir(fullpath):
                utils.copy_files(fullpath, directory)
            else:
                destfile = os.path.join(directory, os.path.basename(self.__workspace))
                utils.safe_copy(fullpath, destfile)

    # Get a unique key for the workspace
    #
    # Note that to avoid re-traversing the file system if this function is
    # called multiple times, the workspace key is cached. You can still force a
    # new calculation to happen by setting the 'recalculate' flag.
    #
    def _get_workspace_key(self, recalculate=False):
        assert not self.__assemble_scheduled

        if recalculate or self.__workspace_key is None:
            fullpath = self._get_workspace_path()

            # Get a list of tuples of the the project relative paths and fullpaths
            if os.path.isdir(fullpath):
                filelist = utils.list_relative_paths(fullpath)
                filelist = [(relpath, os.path.join(fullpath, relpath)) for relpath in filelist]
            else:
                filelist = [(self.__workspace, fullpath)]

            # Return a list of (relative filename, sha256 digest) tuples, a sorted list
            # has already been returned by list_relative_paths()
            self.__workspace_key = [(relpath, _unique_key(fullpath)) for relpath, fullpath in filelist]

        return self.__workspace_key


# Get the sha256 sum for the content of a file
def _unique_key(filename):

    # If it's a directory, just return 0 string
    if os.path.isdir(filename):
        return "0"
    elif os.path.islink(filename):
        return "1"

    try:
        return utils.sha256sum(filename)
    except FileNotFoundError as e:
        raise LoadError(LoadErrorReason.MISSING_FILE,
                        "Failed loading workspace. Did you remove the workspace directory? {}".format(e))
