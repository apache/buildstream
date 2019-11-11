import multiprocessing
import os
import posixpath
import html
import base64
from http.server import SimpleHTTPRequestHandler, HTTPServer, HTTPStatus


class Unauthorized(Exception):
    pass


class RequestHandler(SimpleHTTPRequestHandler):
    def get_root_dir(self):
        authorization = self.headers.get("authorization")
        if not authorization:
            if not self.server.anonymous_dir:
                raise Unauthorized("unauthorized")
            return self.server.anonymous_dir
        else:
            authorization = authorization.split()
            if len(authorization) != 2 or authorization[0].lower() != "basic":
                raise Unauthorized("unauthorized")
            try:
                decoded = base64.decodebytes(authorization[1].encode("ascii"))
                user, password = decoded.decode("ascii").split(":")
                expected_password, directory = self.server.users[user]
                if password == expected_password:
                    return directory
            except:  # noqa
                raise Unauthorized("unauthorized")
            return None

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
        self.send_header("WWW-Authenticate", 'Basic realm="{}"'.format(self.server.realm))
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


class AuthHTTPServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        self.users = {}
        self.anonymous_dir = None
        self.realm = "Realm"
        super().__init__(*args, **kwargs)


class SimpleHttpServer(multiprocessing.Process):
    def __init__(self):
        super().__init__()
        self.server = AuthHTTPServer(("127.0.0.1", 0), RequestHandler)
        self.started = False

    def start(self):
        self.started = True
        super().start()

    def run(self):
        self.server.serve_forever()

    def stop(self):
        if not self.started:
            return
        self.terminate()
        self.join()

    def allow_anonymous(self, cwd):
        self.server.anonymous_dir = cwd

    def add_user(self, user, password, cwd):
        self.server.users[user] = (password, cwd)

    def base_url(self):
        return "http://127.0.0.1:{}".format(self.server.server_port)
