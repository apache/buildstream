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
