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
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream._testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils import override_platform_uname

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "system,value,expected",
    [
        # Test explicitly provided arches
        ("Darwin", "Linux", "Linuxy"),
        ("SunOS", "FreeBSD", "FreeBSDy"),
        # Test automatically derived arches
        ("Linux", None, "Linuxy"),
        ("Darwin", None, "Darwiny"),
        # Test that explicitly provided arches dont error out
        # when the `uname` reported arch is not supported
        ("ULTRIX", "Linux", "Linuxy"),
        ("HaikuOS", "SunOS", "SunOSy"),
    ],
)
def test_conditionals(cli, datafiles, system, value, expected):
    with override_platform_uname(system=system):
        project = os.path.join(datafiles.dirname, datafiles.basename, "option-os")

        bst_args = []
        if value is not None:
            bst_args += ["--option", "machine_os", value]

        bst_args += ["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
        result = cli.run(project=project, silent=True, args=bst_args)
        result.assert_success()

        loaded = _yaml.load_data(result.output)
        assert loaded.get_str("result") == expected


@pytest.mark.datafiles(DATA_DIR)
def test_unsupported_arch(cli, datafiles):

    with override_platform_uname(system="ULTRIX"):
        project = os.path.join(datafiles.dirname, datafiles.basename, "option-os")
        result = cli.run(
            project=project, silent=True, args=["show", "--deps", "none", "--format", "%{vars}", "element.bst"]
        )

        result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
