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
import os
import tarfile

from buildstream.utils import sha256sum

from buildstream._testing import Repo


class Tar(Repo):
    def create(self, directory):
        tarball = os.path.join(self.repo, "file.tar.gz")

        old_dir = os.getcwd()
        os.chdir(directory)
        with tarfile.open(tarball, "w:gz") as tar:
            tar.add(".")
        os.chdir(old_dir)

        return sha256sum(tarball)

    def source_config(self, ref=None):
        tarball = os.path.join(self.repo, "file.tar.gz")
        config = {"kind": "tar", "url": "file://" + tarball, "directory": "", "base-dir": ""}
        if ref is not None:
            config["ref"] = ref

        return config
