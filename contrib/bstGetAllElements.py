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

# This is a helper script for returning all the elements in a project

import os
import yaml

def get_all_buildable_elements():
    elements = []
    cwd = os.getcwd()
    element_path = get_element_path("project.conf")
    for root, _, files in os.walk(cwd):
        for file in files:
            if file.endswith(".bst"):
                relDir = os.path.relpath(root, cwd)
                relFile = os.path.join(relDir, file).strip("./")
                if is_not_junction(relFile):
                    relFile = relFile.replace(element_path, '')
                    elements.append(relFile)
    return elements


def is_not_junction(element):
    try:
        with open(element) as stream:
            data = yaml.load(stream)
            data["junction"]
            return False
    except:
        return True


def get_element_path(project_conf):
    if os.path.isfile(project_conf):
        try:
            with open(project_conf) as stream:
                data = yaml.load(stream)
                data["element-path"]
                return line + '/'
        except:
            return "."
    raise Exception("No project.conf was found in this directory")
