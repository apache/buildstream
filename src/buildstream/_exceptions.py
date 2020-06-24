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

import os

from .exceptions import ErrorDomain

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
    if "BST_TEST_SUITE" not in os.environ:
        raise BstError("Getting the last task error is only supported when running tests")

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
    if "BST_TEST_SUITE" in os.environ:
        global _last_task_error_domain
        global _last_task_error_reason

        _last_task_error_domain = domain
        _last_task_error_reason = reason


# BstError is an internal base exception class for BuildStream
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

        # A sandbox can be created to debug this error
        self.sandbox = False

        # When this exception occurred during the handling of a job, indicate
        # whether or not there is any point retrying the job.
        #
        self.temporary = temporary

        # Error domain and reason
        #
        self.domain = domain
        self.reason = reason

        # Hold on to the last raised exception for testing purposes
        if "BST_TEST_SUITE" in os.environ:
            _last_exception = self


# PluginError
#
# Raised on plugin related errors.
#
# This exception is raised either by the plugin loading process,
# or by the base :class:`.Plugin` element itself.
#
class PluginError(BstError):
    def __init__(self, message, *, reason=None, detail=None, temporary=False):
        super().__init__(message, domain=ErrorDomain.PLUGIN, detail=detail, reason=reason, temporary=temporary)


# LoadError
#
# Raised while loading some YAML.
#
# Args:
#    message (str): human readable error explanation
#    reason (LoadErrorReason): machine readable error reason
#
# This exception is raised when loading or parsing YAML, or when
# interpreting project YAML
#
class LoadError(BstError):
    def __init__(self, message, reason, *, detail=None):
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
    def __init__(self, message, reason=None, detail=None):
        super().__init__(message, domain=ErrorDomain.PLATFORM, reason=reason, detail=detail)


# SandboxError
#
# Raised when errors are encountered by the sandbox implementation
#
class SandboxError(BstError):
    def __init__(self, message, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.SANDBOX, reason=reason)


# AssetCacheError
#
# Raised when errors are encountered in either type of cache
#
class AssetCacheError(BstError):
    def __init__(self, message, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.SANDBOX, reason=reason)


# SourceCacheError
#
# Raised when errors are encountered in the source caches
#
class SourceCacheError(BstError):
    def __init__(self, message, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.SANDBOX, reason=reason)


# ArtifactError
#
# Raised when errors are encountered in the artifact caches
#
class ArtifactError(BstError):
    def __init__(self, message, *, detail=None, reason=None, temporary=False):
        super().__init__(message, detail=detail, domain=ErrorDomain.ARTIFACT, reason=reason, temporary=temporary)


# RemoteError
#
# Raised when errors are encountered in Remotes
#
class RemoteError(BstError):
    def __init__(self, message, *, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.REMOTE, reason=reason)


# CASError
#
# Raised when errors are encountered in the CAS
#
class CASError(BstError):
    def __init__(self, message, *, detail=None, reason=None, temporary=False):
        super().__init__(message, detail=detail, domain=ErrorDomain.CAS, reason=reason, temporary=temporary)


# CASRemoteError
#
# Raised when errors are encountered in the remote CAS
class CASRemoteError(CASError):
    pass


# CASCacheError
#
# Raised when errors are encountered in the local CASCacheError
#
class CASCacheError(CASError):
    pass


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


# CachedFailure
#
# Raised from a child process within a job to indicate that the failure was cached
#
class CachedFailure(BstError):
    pass


# SkipJob
#
# Raised from a child process within a job when the job should be
# considered skipped by the parent process.
#
class SkipJob(Exception):
    pass


# ArtifactElementError
#
# Raised when errors are encountered by artifact elements
#
class ArtifactElementError(BstError):
    def __init__(self, message, *, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.ELEMENT, reason=reason)


# ProfileError
#
# Raised when a user provided profile choice isn't valid
#
class ProfileError(BstError):
    def __init__(self, message, detail=None, reason=None):
        super().__init__(message, detail=detail, domain=ErrorDomain.PROFILE, reason=reason)
