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


class Element():
    """Base Element class.

    All elements derive from this class, this interface defines how
    the core will be interacting with Elements.
    """

    defaults = {}
    """The default configuration for elements of a given *kind*

    Specifies the default configuration for Elements of the given *kind*. The
    class wide default configuration is overridden from other sources, such
    as the Element declarations in the project YAML.
    """
    def __init__(self, context, project, meta):

        self.__context = context                        # The Context object
        self.__project = project                        # The Project object

        self.name = meta.name

        self.configure(meta.config)

    def get_kind(self):
        """Fetches kind of this element

        Returns:
           (str): The kind of this element
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
        """Configure the Element from loaded configuration data

        Args:
           node (dict): The loaded configuration dictionary

        Raises:
           :class:`.LoadError`

        Element implementors should implement this method to read configuration
        data and store it. Use of the the :func:`~buildstream.utils.node_get_member`
        convenience method will ensure that a nice :class:`.LoadError` is triggered
        whenever the YAML input configuration is faulty.
        """
        raise ImplError("Element plugin '%s' does not implement configure()" % self.get_kind())

    def preflight(self):
        """Preflight Check

        Raises:
           :class:`.ElementError`

        The method is run during pipeline preflight check, elements
        should use this method to determine if they are able to
        function in the host environment or if the data is unsuitable.

        Implementors should simply raise :class:`.ElementError` with
        an informative message in the case that the host environment is
        unsuitable for operation.
        """
        raise ImplError("Element plugin '%s' does not implement preflight()" % self.get_kind())

    def get_unique_key(self):
        """Return something which uniquely identifies the element

        Returns:
           A string, list or dictionary which uniquely identifies the element to use
        """
        raise ImplError("Element plugin '%s' does not implement get_unique_key()" % self.get_kind())
