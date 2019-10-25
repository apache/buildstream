import multiprocessing

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


class SimpleFtpServer():
    # pylint: disable=attribute-defined-outside-init

    def __init__(self):
        self._reset()

    def _reset(self):
        self._process = None
        self._port = None
        self._anonymous_dirs = []
        self._user_list = []

    def start(self):
        assert self._process is None, "Server already running."
        queue = multiprocessing.SimpleQueue()

        self._process = multiprocessing.Process(
            target=_run_server,
            args=(queue, self._anonymous_dirs, self._user_list),
        )

        self._process.start()
        self._port = queue.get()

    def stop(self):
        assert self._process is not None, "Server not running."

        # Note that when spawning, terminating in this way will cause us to
        # leak semaphores. This will lead to a warning from Python's semaphore
        # tracker, which will clean them up for us.
        #
        # We could prevent this warning by using alternative methods that would
        # let the _run_server() function finish, the extra complication doesn't
        # seem worth it for this test class.
        #
        self._process.terminate()

        self._process.join()
        self._reset()

    def allow_anonymous(self, cwd):
        assert self._process is None, "Can't modify server after start()."
        self._anonymous_dirs.append(cwd)

    def add_user(self, user, password, cwd):
        assert self._process is None, "Can't modify server after start()."
        self._user_list.append((user, password, cwd))

    def base_url(self):
        assert self._port is not None
        return 'ftp://127.0.0.1:{}'.format(self._port)


def _run_server(queue, anonymous_dirs, user_list):
    authorizer = DummyAuthorizer()
    handler = FTPHandler
    handler.authorizer = authorizer

    for cwd in anonymous_dirs:
        authorizer.add_anonymous(cwd)

    for user, password, cwd in user_list:
        authorizer.add_user(user, password, cwd, perm='elradfmwMT')

    server = FTPServer(('127.0.0.1', 0), handler)

    port = server.address[1]
    queue.put(port)
    server.serve_forever(handle_exit=True)
