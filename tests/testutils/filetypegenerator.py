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
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tiago Gomes <tiago.gomes@codethink.co.uk>

import os
import socket


# generate_file_types()
#
# Generator that creates a regular file directory, symbolic link, fifo
# and socket at the specified path.
#
# Args:
#  path: (str) path where to create each different type of file
#
def generate_file_types(path):
    def clean():
        if os.path.exists(path):
            if os.path.isdir(path):
                os.rmdir(path)
            else:
                os.remove(path)

    clean()

    with open(path, 'w') as f:
        pass
    yield
    clean()

    os.makedirs(path)
    yield
    clean()

    os.symlink("project.conf", path)
    yield
    clean()

    os.mkfifo(path)
    yield
    clean()

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    yield
    clean()
