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
from contextlib import contextmanager

from .ftp_server import SimpleFtpServer
from .http_server import SimpleHttpServer


@contextmanager
def create_file_server(file_server_type):
    if file_server_type == "FTP":
        server = SimpleFtpServer()
    elif file_server_type == "HTTP":
        server = SimpleHttpServer()
    else:
        assert False

    try:
        yield server
    finally:
        server.stop()
