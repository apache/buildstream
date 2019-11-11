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
