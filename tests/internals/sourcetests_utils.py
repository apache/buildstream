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
import shutil
import stat

import pytest

from buildstream import _yaml
from buildstream._testing._sourcetests import utils

PROJECT = os.path.join(os.path.dirname(os.path.realpath(utils.__file__)), "project")


def make_read_only(path):
    for root, _, files in os.walk(path, topdown=False):
        for name in files:
            os.chmod(os.path.join(root, name), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.chmod(root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)


# The shared source tests write into the copy of their project that the
# datafiles fixture makes, which keeps the permissions of the installed files.
@pytest.mark.skipif(os.geteuid() == 0, reason="root can write read-only files")
def test_read_only_project_copy(tmpdir):
    project = os.path.join(str(tmpdir), "project")
    shutil.copytree(PROJECT, project)
    make_read_only(project)

    utils.make_writable(project)

    utils.update_project_configuration(project, {"name": "renamed"})
    assert _yaml.roundtrip_load(os.path.join(project, "project.conf"))["name"] == "renamed"
    with open(os.path.join(project, "elements", "new.bst"), "w", encoding="utf-8") as f:
        f.write("kind: stack\n")
