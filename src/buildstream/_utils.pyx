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


def url_directory_name(str url):
    """Normalizes a url into a directory name

    Args:
       url (str): A url string

    Returns:
       A string which can be used as a directory name
    """
    return ''.join([_transl(x) for x in url])


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
