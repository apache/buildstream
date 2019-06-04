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
#        Benjamin Schubert <bschubert@bloomberg.net>
#


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
