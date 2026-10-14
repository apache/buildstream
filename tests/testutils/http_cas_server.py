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
import functools
import os
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPStatus, ThreadingHTTPServer


class HTTPCASRequestHandler(BaseHTTPRequestHandler):
    HASH_SIZE = 64  # SHA256 as hex digits

    def __init__(self, directory, *args, **kwargs):
        self.objdir = os.path.join(directory, "cas", "objects")
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.process_get_or_head()

    def do_HEAD(self):
        self.process_get_or_head()

    def process_get_or_head(self):
        match = re.fullmatch(r"/cas/([0-9a-f]+)", self.path)
        if match is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        cas_hash = match.group(1)
        if len(cas_hash) != self.HASH_SIZE:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            with open(os.path.join(self.objdir, cas_hash[:2], cas_hash[2:]), "rb") as f:
                fs = os.fstat(f.fileno())

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Length", str(fs.st_size))
                self.end_headers()

                if self.command == "GET":
                    shutil.copyfileobj(f, self.wfile)
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)


class HTTPCASServer(threading.Thread):
    def __init__(self, directory):
        super().__init__()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(HTTPCASRequestHandler, directory))
        self.started = False

    def start(self):
        self.started = True
        super().start()

    def run(self):
        self.server.serve_forever()

    def stop(self):
        if not self.started:
            return
        self.server.shutdown()
        self.join()

    def base_url(self):
        return "http://127.0.0.1:{}".format(self.server.server_port)
