#!/usr/bin/python3
#
#  Copyright 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Phillip Smyth <phillip.smyth@codethink.co.uk>

# This is a helper script for validating all the elements in a project

import os
import bstGetAllElements
import subprocess

def bst_show_all_elements():
    elements = bstGetAllElements.get_all_buildable_elements()
    command = ["bst", "show"] + elements
    subprocess.call(command)

bst_show_all_elements()
