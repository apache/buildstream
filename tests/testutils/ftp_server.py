import multiprocessing

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


class SimpleFtpServer(multiprocessing.Process):
    def __init__(self):
        super().__init__()
        self.authorizer = DummyAuthorizer()
        handler = FTPHandler
        handler.authorizer = self.authorizer
        self.server = FTPServer(("127.0.0.1", 0), handler)

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.close_all()
        self.server.close()
        self.terminate()
        self.join()

    def allow_anonymous(self, cwd):
        self.authorizer.add_anonymous(cwd)

    def add_user(self, user, password, cwd):
        self.authorizer.add_user(user, password, cwd, perm="elradfmwMT")

    def base_url(self):
        return "ftp://127.0.0.1:{}".format(self.server.address[1])
