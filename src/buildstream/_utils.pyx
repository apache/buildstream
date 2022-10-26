#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Benjamin Schubert <bschubert15@bloomberg.net>
#

"""
This module contains utilities that have been optimized in Cython
"""

from cpython.pystate cimport PyThreadState_SetAsyncExc
from cpython.ref cimport PyObject
from ._signals import TerminateException


def url_directory_name(str url):
    """Normalizes a url into a directory name

    Args:
       url (str): A url string

    Returns:
       A string which can be used as a directory name
    """
    return ''.join([_transl(x) for x in url])



# terminate_thread()
#
# Ask a given a given thread to terminate by raising an exception in it.
#
# Args:
#   thread_id (int): the thread id in which to throw the exception
#
def terminate_thread(long thread_id):
    res = PyThreadState_SetAsyncExc(thread_id, <PyObject*> TerminateException)
    assert res == 1


# Check if given filename containers valid characters.
#
# Args:
#    name (str): Name of the file
#
# Returns:
#    (bool): True if all characters are valid, False otherwise.
#
def valid_chars_name(str name):
    cdef int char_value
    cdef int forbidden_char

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
cdef Py_UNICODE _transl(Py_UNICODE x):
    if ("a" <= x <= "z") or ("A" <= x <= "Z") or ("0" <= x <= "9") or x == "%":
        return x
    return "_"


# get_mirror_directory in configure of _downlaodablefilesource
