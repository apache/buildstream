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

from . import _yaml
from . import ImplError
from . import Plugin


class Source(Plugin):
    """Source()

    Base Source class.

    All Sources derive from this class, this interface defines how
    the core will be interacting with Sources.
    """
    def __init__(self, context, project, meta):
        provenance = _yaml.node_get_provenance(meta.config)
        super().__init__(context, project, provenance, "source")

        self.__directory = meta.directory               # Staging relative directory
        self.__origin_node = meta.origin_node           # YAML node this Source was loaded from
        self.__origin_toplevel = meta.origin_toplevel   # Toplevel YAML node for the file
        self.__origin_filename = meta.origin_filename   # Filename of the file the source was loaded from
        self.__consistent = None

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

    def consistent(self):
        """Report whether the source has a resolved reference

        Returns:
           (bool): True if the source has a reference

        Before building, every source must have an exact reference,
        although it is not an error to load a project which contains
        sources that do not have references, they can be fetched
        later with :func:`~buildstream.source.Source.refresh`
        """
        raise ImplError("Source plugin '%s' does not implement consistent()" % self.get_kind())

    def refresh(self, node):
        """Refresh specific source references

        Args:
           node (dict): The same dictionary which was previously passed
                        to :func:`~buildstream.source.Source.configure`

        Returns:
           (bool): True if the refresh resulted in any update or change

        Raises:
           :class:`.SourceError`

        Sources which implement some revision control system should
        implement this by updating the commit reference from a symbolic
        tracking branch or tag. The commit reference should be updated
        internally on the given Source object and also in the passed *node*
        parameter so that a user's project may optionally be updated
        with the new reference.

        Sources which implement a tarball or file should implement this
        by updating an sha256 sum.

        Implementors should raise :class:`.SourceError` if some error is
        encountered while attempting to refresh.
        """
        raise ImplError("Source plugin '%s' does not implement refresh()" % self.get_kind())

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

    # Wrapper for consistent() api which caches the result, we
    # know we're consistent after a successful refresh
    #
    def _consistent(self):

        if self.__consistent is None:
            self.__consistent = self.consistent()

        return self.__consistent

    # Wrapper for refresh()
    #
    def _refresh(self, node):

        changed = self.refresh(node)

        # It's consistent unless it reported an error
        self.__consistent = True

        return changed
