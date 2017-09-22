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
Exceptions
==========
"""

from enum import Enum


# BstError is an internal base exception class for BuildSream
# exceptions.
#
# The sole purpose of using the base class is to add additional
# context to exceptions raised by plugins in child tasks, this
# context can then be communicated back to the main process.
#
class _BstError(Exception):

    def __init__(self, message):
        super(_BstError, self).__init__(message)

        # The build sandbox in which the error occurred, if the
        # error occurred at element assembly time.
        #
        self.sandbox = None


class PluginError(_BstError):
    """Raised on plugin related errors.

    This exception is raised either by the plugin loading process,
    or by the base :class:`.Plugin` element itself.
    """
    pass


class LoadErrorReason(Enum):
    """Describes the reason why a :class:`.LoadError` was raised.
    """

    MISSING_FILE = 1
    """A file was not found."""

    INVALID_YAML = 2
    """The parsed data was not valid YAML."""

    INVALID_DATA = 3
    """Data was malformed, a value was not of the expected type, etc"""

    ILLEGAL_COMPOSITE = 4
    """An error occurred during YAML dictionary composition.

    This can happen by overriding a value with a new differently typed
    value, or by overwriting some named value when that was not allowed.
    """

    CIRCULAR_DEPENDENCY = 5
    """An circular dependency chain was detected"""

    UNRESOLVED_VARIABLE = 6
    """A variable could not be resolved. This can happen if your project
    has cyclic dependencies in variable declarations, or, when substituting
    a string which refers to an undefined variable.
    """

    UNSUPPORTED_PROJECT = 7
    """BuildStream does not support the required project format version"""


class LoadError(_BstError):
    """Raised while loading some YAML.

    This exception is raised when loading or parsing YAML, or when
    interpreting project YAML
    """
    def __init__(self, reason, message):
        super(LoadError, self).__init__(message)

        self.reason = reason
        """The :class:`.LoadErrorReason` for which this exception was raised
        """


class SourceError(_BstError):
    """Raised by Source implementations.

    This exception is raised when a :class:`.Source` encounters an error.
    """
    pass


class ElementError(_BstError):
    """Raised by Element implementations.

    This exception is raised when an :class:`.Element` encounters an error.
    """
    pass


class ImplError(_BstError):
    """Raised when a :class:`.Source` or :class:`.Element` plugin fails to
    implement a mandatory method"""
    pass


class ProgramNotFoundError(_BstError):
    """Raised if a required program is not found

    BuildSource requires various software to exist on the host for
    it to work correctly. This exception is thrown if that software
    can not be found. E.g. The :class:`.Sandbox` class expects that
    bubblewrap is installed for it to work.
    """
    pass


class PlatformError(_BstError):
    """Raised if the current platform is not supported.
    """
    pass


class _ArtifactError(_BstError):
    pass
