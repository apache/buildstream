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

    with open(path, "w", encoding="utf-8"):
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

    # Change directory because the full path may be longer than the ~100
    # characters permitted for a unix socket
    old_dir = os.getcwd()
    parent, child = os.path.split(path)
    os.chdir(parent)

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    try:
        s.bind(child)
        os.chdir(old_dir)
        yield
    finally:
        s.close()

    clean()
