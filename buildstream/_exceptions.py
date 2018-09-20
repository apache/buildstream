#
#  Copyright (C) 2018 Codethink Limited
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
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

from enum import Enum

# Disable pylint warnings for whole file here:
# pylint: disable=global-statement

# The last raised exception, this is used in test cases only
_last_exception = None
_last_task_error_domain = None
_last_task_error_reason = None


# get_last_exception()
#
# Fetches the last exception from the main process
#
# Used by regression tests
#
def get_last_exception():
    global _last_exception

    le = _last_exception
    _last_exception = None
    return le


# get_last_task_error()
#
# Fetches the last exception from a task
#
# Used by regression tests
#
def get_last_task_error():
    global _last_task_error_domain
    global _last_task_error_reason

    d = _last_task_error_domain
    r = _last_task_error_reason
    _last_task_error_domain = _last_task_error_reason = None
    return (d, r)


# set_last_task_error()
#
# Sets the last exception of a task
#
# This is set by some internals to inform regression
# tests about how things failed in a machine readable way
#
def set_last_task_error(domain, reason):
    global _last_task_error_domain
    global _last_task_error_reason

    _last_task_error_domain = domain
    _last_task_error_reason = reason


class ErrorDomain(Enum):
    PLUGIN = 1
    LOAD = 2
    IMPL = 3
    PLATFORM = 4
    SANDBOX = 5
    ARTIFACT = 6
    PIPELINE = 7
    OSTREE = 8
    UTIL = 9
    PROG_NOT_FOUND = 12
    SOURCE = 10
    ELEMENT = 11
    APP = 12
    STREAM = 13


# BstError is an internal base exception class for BuildSream
# exceptions.
#
# The sole purpose of using the base class is to add additional
# context to exceptions raised by plugins in child tasks, this
# context can then be communicated back to the main process.
#
class BstError(Exception):

    def __init__(self, message, *, detail=None, domain=None, reason=None, temporary=False):
        global _last_exception

        super().__init__(message)

        # Additional error detail, these are used to construct detail
        # portions of the logging messages when encountered.
        #
        self.detail = detail

        # The build sandbox in which the error occurred, if the
        # error occurred at element assembly time.
        #
        self.sandbox = None

        # When this exception occurred during the handling of a job, indicate
        # whether or not there is any point retrying the job.
        #
        self.temporary = temporary

        # Error domain and reason
        #
        self.domain = domain
        self.reason = reason

        # Hold on to the last raised exception for testing purposes
        _last_exception = self


# PluginError
#
# Raised on plugin related errors.
#
# This exception is raised either by the plugin loading process,
# or by the base :class:`.Plugin` element itself.
#
class PluginError(BstError):
    def __init__(self, message, reason=None, temporary=False):
        super().__init__(message, domain=ErrorDomain.PLUGIN, reason=reason, temporary=False)


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

    # Project requires a newer version of a plugin than the one which was loaded
    UNSUPPORTED_PLUGIN = 8

    # A conditional expression failed to resolve
    EXPRESSION_FAILED = 9

    # An assertion was intentionally encoded into project YAML
    USER_ASSERTION = 10

    # A list composition directive did not apply to any underlying list
    TRAILING_LIST_DIRECTIVE = 11

    # Conflicting junctions in subprojects
    CONFLICTING_JUNCTION = 12

    # Failure to load a project from a specified junction
    INVALID_JUNCTION = 13

    # Subproject needs to be fetched
    SUBPROJECT_FETCH_NEEDED = 14

    # Subproject has no ref
    SUBPROJECT_INCONSISTENT = 15

    # An invalid symbol name was encountered
    INVALID_SYMBOL_NAME = 16

    # A project.conf file was missing
    MISSING_PROJECT_CONF = 17

    # Try to load a directory not a yaml file
    LOADING_DIRECTORY = 18

    # A project path leads outside of the project directory
    PROJ_PATH_INVALID = 19

    # A project path points to a file of the not right kind (e.g. a
    # socket)
    PROJ_PATH_INVALID_KIND = 20

    # A recursive include has been encountered.
    RECURSIVE_INCLUDE = 21

    # A recursive variable has been encountered
    RECURSIVE_VARIABLE = 22

    # An attempt so set the value of a protected variable
    PROTECTED_VARIABLE_REDEFINED = 23


# LoadError
#
# Raised while loading some YAML.
#
# Args:
#    reason (LoadErrorReason): machine readable error reason
#    message (str): human readable error explanation
#
# This exception is raised when loading or parsing YAML, or when
# interpreting project YAML
#
class LoadError(BstError):
    def __init__(self, reason, message, *, detail=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.LOAD, reason=reason)


# ImplError
#
# Raised when a :class:`.Source` or :class:`.Element` plugin fails to
# implement a mandatory method
#
class ImplError(BstError):
    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.IMPL, reason=reason)


# PlatformError
#
# Raised if the current platform is not supported.
class PlatformError(BstError):
    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.PLATFORM, reason=reason)


# SandboxError
#
# Raised when errors are encountered by the sandbox implementation
#
class SandboxError(BstError):
    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.SANDBOX, reason=reason)


# ArtifactError
#
# Raised when errors are encountered in the artifact caches
#
class ArtifactError(BstError):
    def __init__(self, message, *, detail=None, reason=None, temporary=False):
        super().__init__(message, detail=detail, domain=ErrorDomain.ARTIFACT, reason=reason, temporary=True)


# PipelineError
#
# Raised from pipeline operations
#
class PipelineError(BstError):

    def __init__(self, message, *, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.PIPELINE, reason=reason)


# StreamError
#
# Raised when a stream operation fails
#
class StreamError(BstError):

    def __init__(self, message=None, *, detail=None, reason=None, terminated=False):

        # The empty string should never appear to a user,
        # this only allows us to treat this internal error as
        # a BstError from the frontend.
        if message is None:
            message = ""

        super().__init__(message, detail=detail, domain=ErrorDomain.STREAM, reason=reason)

        self.terminated = terminated


# AppError
#
# Raised from the frontend App directly
#
class AppError(BstError):
    def __init__(self, message, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.APP, reason=reason)


# SkipJob
#
# Raised from a child process within a job when the job should be
# considered skipped by the parent process.
#
class SkipJob(Exception):
    pass
