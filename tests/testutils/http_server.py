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
        authorization = self.headers.get('authorization')
        if not authorization:
            if not self.server.anonymous_dir:
                raise Unauthorized('unauthorized')
            return self.server.anonymous_dir
        else:
            authorization = authorization.split()
            if len(authorization) != 2 or authorization[0].lower() != 'basic':
                raise Unauthorized('unauthorized')
            try:
                decoded = base64.decodebytes(authorization[1].encode('ascii'))
                user, password = decoded.decode('ascii').split(':')
                expected_password, directory = self.server.users[user]
                if password == expected_password:
                    return directory
            except:                           # noqa
                raise Unauthorized('unauthorized')
            return None

    def unauthorized(self):
        shortmsg, longmsg = self.responses[HTTPStatus.UNAUTHORIZED]
        self.send_response(HTTPStatus.UNAUTHORIZED, shortmsg)
        self.send_header('Connection', 'close')

        content = (self.error_message_format % {
            'code': HTTPStatus.UNAUTHORIZED,
            'message': html.escape(longmsg, quote=False),
            'explain': html.escape(longmsg, quote=False)
        })
        body = content.encode('UTF-8', 'replace')
        self.send_header('Content-Type', self.error_content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('WWW-Authenticate', 'Basic realm="{}"'.format(self.server.realm))
        self.end_headers()
        self.end_headers()

        if self.command != 'HEAD' and body:
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
        path = path.split('?', 1)[0]
        path = path.split('#', 1)[0]
        path = posixpath.normpath(path)
        assert posixpath.isabs(path)
        path = posixpath.relpath(path, '/')
        return os.path.join(self.get_root_dir(), path)


class AuthHTTPServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        self.users = {}
        self.anonymous_dir = None
        self.realm = 'Realm'
        super().__init__(*args, **kwargs)


class SimpleHttpServer():
    # pylint: disable=attribute-defined-outside-init

    def __init__(self):
        self._reset()

    def _reset(self):
        self._process = None
        self._port = None
        self._anonymous_dir = None
        self._user_list = []

    def start(self):
        assert self._process is None, "Server already running."
        queue = multiprocessing.SimpleQueue()

        self._process = multiprocessing.Process(
            target=_run_server,
            args=(queue, self._anonymous_dir, self._user_list),
        )

        self._process.start()
        self._port = queue.get()

    def stop(self):
        assert self._process is not None, "Server not running."
        self._process.terminate()
        self._process.join()
        self._reset()

    def allow_anonymous(self, cwd):
        assert self._process is None, "Can't modify server after start()."
        assert self._anonymous_dir is None, "Only one anonymous_dir is supported."
        self._anonymous_dir = cwd

    def add_user(self, user, password, cwd):
        assert self._process is None, "Can't modify server after start()."
        self._user_list.append((user, password, cwd))

    def base_url(self):
        assert self._port is not None
        return 'http://127.0.0.1:{}'.format(self._port)


def _run_server(queue, anonymous_dir, user_list):
    server = AuthHTTPServer(('127.0.0.1', 0), RequestHandler)

    if anonymous_dir is not None:
        server.anonymous_dir = anonymous_dir

    for user, password, cwd in user_list:
        server.users[user] = (password, cwd)

    queue.put(server.server_port)

    server.serve_forever()
