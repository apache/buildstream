#
#  Copyright (C) 2019 Bloomberg L.P.
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
#        Benjamin Schubert <bschubert15@bloomberg.net>
#

"""
This module contains utilities that have been optimized in Cython
"""

import cython  # pylint: disable=import-error
from cython.cimports.cpython.pystate import PyThreadState_SetAsyncExc  # pylint: disable=import-error
from cython.cimports.cpython.ref import PyObject  # pylint: disable=import-error
from ._signals import TerminateException


def url_directory_name(url: str):
    """Normalizes a url into a directory name

    Args:
       url (str): A url string

    Returns:
       A string which can be used as a directory name
    """
    return "".join([_transl(x) for x in url])


# terminate_thread()
#
# Ask a given a given thread to terminate by raising an exception in it.
#
# Args:
#   thread_id (int): the thread id in which to throw the exception
#
def terminate_thread(thread_id: cython.long):
    res = PyThreadState_SetAsyncExc(thread_id, cython.cast(cython.pointer(PyObject), TerminateException))
    assert res == 1


# Check if given filename containers valid characters.
#
# Args:
#    name (str): Name of the file
#
# Returns:
#    (bool): True if all characters are valid, False otherwise.
#
def valid_chars_name(name: str):
    char_value: cython.int
    forbidden_char: cython.int

    for char_value in name:
        # 0-31 are control chars, 127 is DEL, and >127 means non-ASCII
        if char_value <= 31 or char_value >= 127:
            return False

        # Disallow characters that are invalid on Windows. The list can be
        # found at https://docs.microsoft.com/en-us/windows/desktop/FileIO/naming-a-file
        #
        # Note that although : (colon) is not allowed, we do not raise
        # warnings because of that, since we use it as a separator for
        # junctioned elements.
        #
        # We also do not raise warnings on slashes since they are used as
        # path separators.
        for forbidden_char in '<>"|?*':
            if char_value == forbidden_char:
                return False

    return True


#############################################################
#                 Module local helper Methods               #
#############################################################


# _transl(x)
#
# Helper for `url_directory_name`
#
# This transforms the value to "_" if is it not a ascii letter, a digit or "%" or "_"
#
@cython.cfunc
def _transl(x: cython.Py_UNICODE) -> cython.Py_UNICODE:
    if ("a" <= x <= "z") or ("A" <= x <= "Z") or ("0" <= x <= "9") or x == "%":
        return x
    return "_"


# get_mirror_directory in configure of _downlaodablefilesource
