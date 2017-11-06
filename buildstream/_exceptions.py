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

from enum import Enum


# The last raised exception, this is used in test cases only
_last_exception = None


def _get_last_exception():
    global _last_exception

    le = _last_exception
    _last_exception = None
    return le


# BstError is an internal base exception class for BuildSream
# exceptions.
#
# The sole purpose of using the base class is to add additional
# context to exceptions raised by plugins in child tasks, this
# context can then be communicated back to the main process.
#
class _BstError(Exception):

    def __init__(self, message):
        global _last_exception

        super(_BstError, self).__init__(message)

        # The build sandbox in which the error occurred, if the
        # error occurred at element assembly time.
        #
        self.sandbox = None

        # Hold on to the last raised exception for testing purposes
        _last_exception = self


# PluginError
#
# Raised on plugin related errors.
#
# This exception is raised either by the plugin loading process,
# or by the base :class:`.Plugin` element itself.
#
class PluginError(_BstError):
    pass


# LoadErrorReason
#
# Describes the reason why a :class:`.LoadError` was raised.
#
class LoadErrorReason(Enum):

    # A file was not found.
    MISSING_FILE = 1

    # The parsed data was not valid YAML.
    INVALID_YAML = 2

    # Data was malformed, a value was not of the expected type, etc
    INVALID_DATA = 3

    # An error occurred during YAML dictionary composition.
    #
    # This can happen by overriding a value with a new differently typed
    # value, or by overwriting some named value when that was not allowed.
    ILLEGAL_COMPOSITE = 4

    # An circular dependency chain was detected
    CIRCULAR_DEPENDENCY = 5

    # A variable could not be resolved. This can happen if your project
    # has cyclic dependencies in variable declarations, or, when substituting
    # a string which refers to an undefined variable.
    UNRESOLVED_VARIABLE = 6

    # BuildStream does not support the required project format version
    UNSUPPORTED_PROJECT = 7

    # A conditional expression failed to resolve
    EXPRESSION_FAILED = 8

    # An assertion was intentionally encoded into project YAML
    USER_ASSERTION = 9

    # A list composition directive did not apply to any underlying list
    TRAILING_LIST_DIRECTIVE = 10


# LoadError
#
# Raised while loading some YAML.
#
# This exception is raised when loading or parsing YAML, or when
# interpreting project YAML
#
class LoadError(_BstError):
    def __init__(self, reason, message):
        super(LoadError, self).__init__(message)

        # The :class:`.LoadErrorReason` for which this exception was raised
        #
        self.reason = reason


# ImplError
#
# Raised when a :class:`.Source` or :class:`.Element` plugin fails to
# implement a mandatory method
#
class ImplError(_BstError):
    pass


# ProgramNotFoundError
#
# Raised if a required program is not found
#
# BuildStream requires various software to exist on the host for
# it to work correctly. This exception is thrown if that software
# can not be found. E.g. The :class:`.Sandbox` class expects that
# bubblewrap is installed for it to work.
#
class ProgramNotFoundError(_BstError):
    pass


# PlatformError
#
# Raised if the current platform is not supported.
class PlatformError(_BstError):
    pass


# SandboxError
#
# Raised when errors are encountered by the sandbox implementation
#
class SandboxError(_BstError):
    pass


# ArtifactError
#
# Raised when errors are encountered in the artifact caches
#
class _ArtifactError(_BstError):
    pass
