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
"""
Exceptions - API for Error Handling
===================================

This module contains some Enums used in Error Handling which are useful in
testing external plugins.
"""

from enum import Enum, unique


@unique
class ErrorDomain(Enum):
    """ErrorDomain

    Describes what the error is related to.
    """

    PLUGIN = 1
    LOAD = 2
    IMPL = 3
    PLATFORM = 4
    SANDBOX = 5
    ARTIFACT = 6
    PIPELINE = 7
    UTIL = 8
    SOURCE = 9
    ELEMENT = 10
    APP = 11
    STREAM = 12
    VIRTUAL_FS = 13
    CAS = 14
    PROG_NOT_FOUND = 15
    REMOTE = 16
    PROFILE = 17


class LoadErrorReason(Enum):
    """LoadErrorReason

    Describes the reason why a :class:`.LoadError` was raised.
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
    """A circular dependency chain was detected"""

    UNRESOLVED_VARIABLE = 6
    """A variable could not be resolved. This can happen if your project
    has cyclic dependencies in variable declarations, or, when substituting
    a string which refers to an undefined variable.
    """

    UNSUPPORTED_PROJECT = 7
    """The project requires an incompatible BuildStream version"""

    UNSUPPORTED_PLUGIN = 8
    """Project requires a newer version of a plugin than the one which was
    loaded
    """

    EXPRESSION_FAILED = 9
    """A conditional expression failed to resolve"""

    USER_ASSERTION = 10
    """An assertion was intentionally encoded into project YAML"""

    TRAILING_LIST_DIRECTIVE = 11
    """A list composition directive did not apply to any underlying list"""

    CONFLICTING_JUNCTION = 12
    """Conflicting junctions in subprojects"""

    INVALID_JUNCTION = 13
    """Failure to load a project from a specified junction"""

    SUBPROJECT_INCONSISTENT = 15
    """Subproject has no ref"""

    INVALID_SYMBOL_NAME = 16
    """An invalid symbol name was encountered"""

    MISSING_PROJECT_CONF = 17
    """A project.conf file was missing"""

    LOADING_DIRECTORY = 18
    """Try to load a directory not a yaml file"""

    PROJ_PATH_INVALID = 19
    """A project path leads outside of the project directory"""

    PROJ_PATH_INVALID_KIND = 20
    """A project path points to a file of the not right kind (e.g. a
    socket)
    """

    RECURSIVE_INCLUDE = 21
    """A recursive include has been encountered"""

    CIRCULAR_REFERENCE_VARIABLE = 22
    """A circular variable reference was detected"""

    PROTECTED_VARIABLE_REDEFINED = 23
    """An attempt was made to set the value of a protected variable"""

    DUPLICATE_DEPENDENCY = 24
    """A duplicate dependency was detected"""

    LINK_FORBIDDEN_DEPENDENCIES = 25
    """A link element declared dependencies"""

    CIRCULAR_REFERENCE = 26
    """A circular element reference was detected"""
