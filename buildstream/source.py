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

from . import ImplError


class Source():
    """Source()

    Base Source class.

    All Sources derive from this class, this interface defines how
    the core will be interacting with Sources.
    """
    def __init__(self, context, project, meta):

        self.__context = context                        # The Context object
        self.__project = project                        # The Project object
        self.__directory = meta.directory               # Staging relative directory
        self.__origin_node = meta.origin_node           # YAML node this Source was loaded from
        self.__origin_toplevel = meta.origin_toplevel   # Toplevel YAML node for the file
        self.__origin_filename = meta.origin_filename   # Filename of the file the source was loaded from

        self.configure(meta.config)

    def get_kind(self):
        """Fetches kind of this source

        Returns:
           (str): The kind of this source
        """
        modulename = type(self).__module__
        return modulename.split('.')[-1]

    def get_context(self):
        """Fetches the context

        Returns:
           (object): The :class:`.Context`
        """
        return self.__context

    def get_project(self):
        """Fetches the project

        Returns:
           (object): The :class:`.Project`
        """
        return self.__project

    def configure(self, node):
        """Configure the Source from loaded configuration data

        Args:
           node (dict): The loaded configuration dictionary

        Raises:
           :class:`.LoadError`

        Source implementors should implement this method to read configuration
        data and store it. Use of the the :func:`~buildstream.utils.node_get_member`
        convenience method will ensure that a nice :class:`.LoadError` is triggered
        whenever the YAML input configuration is faulty.
        """
        raise ImplError("Source plugin '%s' does not implement configure()" % self.get_kind())

    def preflight(self):
        """Preflight Check

        Raises:
           :class:`.PreflightError`

        The method is run during pipeline preflight check, sources
        should use this method to determine if they are able to
        function in the host environment or if the data is unsuitable.

        Sources should check for the presence of any host tooling they may
        require to fetch source code, and also whether a specific ref
        has been chosen which could be obtained by running refresh.

        Implementors should simply raise :class:`.PreflightError` with
        an informative message in the case that the host environment is
        unsuitable for operation.
        """
        raise ImplError("Source plugin '%s' does not implement preflight()" % self.get_kind())

    def refresh(self, node):
        """Refresh specific source references

        Args:
           node (dict): The same dictionary which was previously passed
                        to :func:`~buildstream.source.Source.configure`

        Sources which implement some revision control system should
        implement this by updating the commit reference from a symbolic
        tracking branch or tag. The commit reference should be updated
        internally on the given Source object and also in the passed *node*
        parameter so that a user's project may optionally be updated
        with the new reference.

        Sources which implement a tarball or file should implement this
        by updating an sha256 sum.
        """
        raise ImplError("Source plugin '%s' does not implement refresh()" % self.get_kind())

    def get_unique_key(self):
        """Return something which uniquely identifies the source

        Returns:
           A string, list or dictionary which uniquely identifies the sources to use

        Implementors can usually implement this by returning a string which
        the uniquely depicts the source, for instance a git sha or an sha256 sum
        of a tarball.

        Implementors can expect that by this time an exact source reference has
        been obtained as we have passed the :func:`~buildstream.source.Source.preflight`
        stage and :func:`~buildstream.source.Source.refresh` was called if necessary.
        """
        raise ImplError("Source plugin '%s' does not implement enrich_key()" % self.get_kind())

    def fetch(self):
        """Fetch remote sources and mirror them locally, ensuring at least
        that the specific reference is cached locally.

        Raises:
           :class:`.FetchError`

        Implementors should raise :class:`.FetchError` if the there is some
        network error or if the source reference could not be matched.
        """
        raise ImplError("Source plugin '%s' does not implement fetch()" % self.get_kind())

    def stage(self, directory):
        """Stage the sources to a directory

        Args:
           directory (str): Path to stage the source

        Implementors should assume that *directory* already exists
        and stage already cached sources to the passed directory.
        Hardlinks should be employed if possible.
        """
        raise ImplError("Source plugin '%s' does not implement stage()" % self.get_kind())
