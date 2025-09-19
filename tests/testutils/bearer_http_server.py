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
import threading
import os
import posixpath
import html
from http.server import SimpleHTTPRequestHandler, HTTPServer, HTTPStatus


class Unauthorized(Exception):
    pass


class BearerRequestHandler(SimpleHTTPRequestHandler):
    def get_root_dir(self):
        authorization = self.headers.get("authorization")
        if not authorization:
            raise Unauthorized("unauthorized")

        authorization = authorization.split()
        if len(authorization) != 2 or authorization[0].lower() != "bearer":
            raise Unauthorized("unauthorized")

        token = authorization[1]
        if token not in self.server.tokens:
            raise Unauthorized("unauthorized")

        return self.server.directory

    def unauthorized(self):
        shortmsg, longmsg = self.responses[HTTPStatus.UNAUTHORIZED]
        self.send_response(HTTPStatus.UNAUTHORIZED, shortmsg)
        self.send_header("Connection", "close")

        content = self.error_message_format % {
            "code": HTTPStatus.UNAUTHORIZED,
            "message": html.escape(longmsg, quote=False),
            "explain": html.escape(longmsg, quote=False),
        }
        body = content.encode("UTF-8", "replace")
        self.send_header("Content-Type", self.error_content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("WWW-Authenticate", 'Bearer realm="{}"'.format(self.server.realm))
        self.end_headers()
        self.end_headers()

        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def do_GET(self):
        try:
            super().do_GET()
        except Unauthorized:
            self.unauthorized()

    def do_HEAD(self):
        try:
            super().do_HEAD()
        except Unauthorized:
            self.unauthorized()

    def translate_path(self, path):
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]
        path = posixpath.normpath(path)
        assert posixpath.isabs(path)
        path = posixpath.relpath(path, "/")
        return os.path.join(self.get_root_dir(), path)


class BearerHTTPServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        self.tokens = set()
        self.directory = None
        self.realm = "Realm"
        super().__init__(*args, **kwargs)


class BearerHttpServer(threading.Thread):
    def __init__(self):
        super().__init__()
        self.server = BearerHTTPServer(("127.0.0.1", 0), BearerRequestHandler)
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

    def set_directory(self, directory):
        self.server.directory = directory

    def add_token(self, token):
        self.server.tokens.add(token)

    def base_url(self):
        return "http://127.0.0.1:{}".format(self.server.server_port)
