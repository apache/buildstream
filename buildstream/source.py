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

import os
import tempfile
import shutil
from contextlib import contextmanager

from . import _yaml, _signals
from . import ImplError
from . import Plugin


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


class Source(Plugin):
    """Source()

    Base Source class.

    All Sources derive from this class, this interface defines how
    the core will be interacting with Sources.
    """
    def __init__(self, context, project, meta):
        provenance = _yaml.node_get_provenance(meta.config)
        super().__init__(meta.name, context, project, provenance, "source")

        self.__directory = meta.directory               # Staging relative directory
        self.__origin_node = meta.origin_node           # YAML node this Source was loaded from
        self.__origin_toplevel = meta.origin_toplevel   # Toplevel YAML node for the file
        self.__origin_filename = meta.origin_filename   # Filename of the file the source was loaded from
        self.__consistency = None                       # Cached consistency state

        self.configure(meta.config)

    def get_mirror_directory(self):
        """Fetches the directory where this source should store things

        Returns:
           (str): The directory belonging to this source
        """

        # Create the directory if it doesnt exist
        context = self.get_context()
        directory = os.path.join(context.sourcedir, self.get_kind())
        os.makedirs(directory, exist_ok=True)
        return directory

    @contextmanager
    def tempdir(self):
        """Context manager for working in a temporary directory

        Yields:
           (str): A path to a temporary directory

        This should be used by source plugins directly instead of the
        tempfile module, as it will take care of cleaning up the temporary
        directory in the case of forced termination.
        """
        mirrordir = self.get_mirror_directory()
        tempdir = tempfile.mkdtemp(dir=mirrordir)

        def cleanup_tempdir():
            if os.path.isdir(tempdir):
                shutil.rmtree(tempdir)

        with _signals.terminator(cleanup_tempdir):
            yield tempdir

        cleanup_tempdir()

    def get_consistency(self):
        """Report whether the source has a resolved reference

        Returns:
           (:class:`.Consistency`): The source consistency
        """
        raise ImplError("Source plugin '%s' does not implement get_consistency()" % self.get_kind())

    def get_ref(self):
        """Fetch the internal ref, however it is represented

        Returns:
           (simple object): The internal source reference

        Note:
           The reference is the user provided (or track resolved) value
           the plugin uses to represent a specific input, like a commit
           in a VCS or a tarball's checksum. Usually the reference is a string,
           but the plugin may choose to represent it with a tuple or such.
        """
        raise ImplError("Source plugin '%s' does not implement get_ref()" % self.get_kind())

    def set_ref(self, ref, node):
        """Applies the internal ref, however it is represented

        Args:
           ref (simple object): The internal source reference to set
           node (dict): The same dictionary which was previously passed
                        to :func:`~buildstream.source.Source.configure`

        See :func:`~buildstream.source.Source.get_ref` for a discussion on
        the *ref* parameter.
        """
        raise ImplError("Source plugin '%s' does not implement set_ref()" % self.get_kind())

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
        raise ImplError("Source plugin '%s' does not implement fetch()" % self.get_kind())

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
        raise ImplError("Source plugin '%s' does not implement stage()" % self.get_kind())

    #############################################################
    #            Private Methods used in BuildStream            #
    #############################################################

    # Wrapper for get_consistency() api which caches the result
    #
    def _get_consistency(self, recalculate=False):
        if recalculate or self.__consistency is None:
            self.__consistency = self.get_consistency()
        return self.__consistency

    # Bump local cached consistency state, this is done from
    # the pipeline after the successful completion of fetch
    # and track jobs.
    #
    def _bump_consistency(self, consistency):
        if (self.__consistency is None or
            consistency > self.__consistency):
            self.__consistency = consistency

    # Force a source to appear to be in an inconsistent state.
    #
    # This is used across the pipeline in sessions where the
    # source in question are going to be tracked. This is important
    # as it will prevent depending elements from producing cache
    # keys until the source is RESOLVED and also prevent depending
    # elements from being assembled until the source is CACHED.
    #
    def _force_inconsistent(self):
        self.__consistency = Consistency.INCONSISTENT

    # Wrapper function around plugin provided fetch method
    #
    def _fetch(self):
        self.fetch()

    # Wrapper for stage() api which gives the source
    # plugin a fully constructed path considering the
    # 'directory' option
    #
    def _stage(self, directory):
        if self.__directory is not None:
            directory = os.path.join(directory, self.__directory.lstrip(os.sep))
        os.makedirs(directory, exist_ok=True)
        self.stage(directory)

    # Wrapper for set_ref(), also returns whether it changed.
    #
    def _set_ref(self, ref, node):
        current_ref = self.get_ref()
        changed = False

        # This comparison should work even for tuples and lists,
        # but we're mostly concerned about simple strings anyway.
        if current_ref != ref:
            self.set_ref(ref, node)
            changed = True

        return changed

    # Wrapper for track()
    #
    def _track(self):
        new_ref = self.track()
        current_ref = self.get_ref()

        # It's consistent unless it reported an error
        self._bump_consistency(Consistency.RESOLVED)
        if current_ref != new_ref:
            self.info("Found new revision: {}".format(new_ref))

        return new_ref
