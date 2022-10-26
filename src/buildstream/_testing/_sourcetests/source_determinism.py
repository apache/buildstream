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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml
from .._utils.site import HAVE_SANDBOX, CASD_SEPARATE_USER
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import kind  # pylint: disable=unused-import

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def create_test_file(*path, mode=0o644, content="content\n"):
    path = os.path.join(*path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        os.fchmod(f.fileno(), mode)


def create_test_directory(*path, mode=0o644):
    create_test_file(*path, ".keep", content="")
    path = os.path.join(*path)
    os.chmod(path, mode)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_deterministic_source_umask(cli, tmpdir, datafiles, kind):
    if CASD_SEPARATE_USER and kind == "ostree":
        pytest.xfail("The ostree plugin ignores the umask")

    project = str(datafiles)
    element_name = "list.bst"
    element_path = os.path.join(project, "elements", element_name)
    repodir = os.path.join(str(tmpdir), "repo")
    sourcedir = os.path.join(project, "source")

    create_test_file(sourcedir, "a.txt", mode=0o700)
    create_test_file(sourcedir, "b.txt", mode=0o755)
    create_test_file(sourcedir, "c.txt", mode=0o600)
    create_test_file(sourcedir, "d.txt", mode=0o400)
    create_test_file(sourcedir, "e.txt", mode=0o644)
    create_test_file(sourcedir, "f.txt", mode=0o4755)
    create_test_file(sourcedir, "g.txt", mode=0o2755)
    create_test_file(sourcedir, "h.txt", mode=0o1755)
    create_test_directory(sourcedir, "dir-a", mode=0o0700)
    create_test_directory(sourcedir, "dir-c", mode=0o0755)
    create_test_directory(sourcedir, "dir-d", mode=0o4755)
    create_test_directory(sourcedir, "dir-e", mode=0o2755)
    create_test_directory(sourcedir, "dir-f", mode=0o1755)

    repo = create_repo(kind, repodir)
    ref = repo.create(sourcedir)
    source = repo.source_config(ref=ref)
    element = {
        "kind": "manual",
        "depends": [{"filename": "base.bst", "type": "build"}],
        "sources": [source],
        "config": {"install-commands": ['ls -l >"%{install-root}/ls-l"']},
    }
    _yaml.roundtrip_dump(element, element_path)

    def get_value_for_umask(umask):
        checkoutdir = os.path.join(str(tmpdir), "checkout-{}".format(umask))

        old_umask = os.umask(umask)

        try:
            test_values = []
            result = cli.run(project=project, args=["build", element_name])
            result.assert_success()

            result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkoutdir])
            result.assert_success()

            with open(os.path.join(checkoutdir, "ls-l"), "r", encoding="utf-8") as f:
                for line in f.readlines():
                    test_values.append(line.split()[0] + " " + line.split()[-1])
                return test_values
        finally:
            os.umask(old_umask)
            cli.remove_artifact_from_cache(project, element_name)

    if CASD_SEPARATE_USER:
        # buildbox-casd running as separate user of the same group can't
        # function in a test environment with a too restrictive umask.
        assert get_value_for_umask(0o002) == get_value_for_umask(0o007)
    else:
        assert get_value_for_umask(0o022) == get_value_for_umask(0o077)
