#
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing.runcli import cli  # pylint: disable=unused-import
from buildstream import _yaml

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
def test_patch_sources_cached_1(cli, datafiles):
    project_dir = str(datafiles)

    res = cli.run(project=project_dir, args=["build", "source-with-patches-1.bst"])
    res.assert_success()

    # as we have a local, patch, local config, the first local and patch should
    # be cached together, and the last local on it's own
    source_protos = os.path.join(project_dir, "cache", "source_protos")

    assert len(os.listdir(os.path.join(source_protos, "patch"))) == 1
    assert len(os.listdir(os.path.join(source_protos, "local"))) == 2


@pytest.mark.datafiles(DATA_DIR)
def test_patch_sources_cached_2(cli, datafiles):
    project_dir = str(datafiles)

    res = cli.run(project=project_dir, args=["build", "source-with-patches-2.bst"])
    res.assert_success()

    # As everything is before the patch it should all be cached together
    source_protos = os.path.join(project_dir, "cache", "source_protos")

    assert len(os.listdir(os.path.join(source_protos, "patch"))) == 1


@pytest.mark.datafiles(DATA_DIR)
def test_sources_without_patch(cli, datafiles):
    project_dir = str(datafiles)

    res = cli.run(project=project_dir, args=["build", "source-without-patches.bst"])
    res.assert_success()

    # No patches so everything should be cached seperately
    source_protos = os.path.join(project_dir, "cache", "source_protos")

    assert len(os.listdir(os.path.join(source_protos, "local"))) == 3


@pytest.mark.datafiles(DATA_DIR)
def test_source_cache_key(cli, datafiles):
    project_dir = str(datafiles)

    file_path = os.path.join(project_dir, "files")
    file_url = "file://" + file_path
    element_path = os.path.join(project_dir, "elements")
    element_name = "key_check.bst"
    element = {
        "kind": "import",
        "sources": [
            {
                "kind": "remote",
                "url": os.path.join(file_url, "bin-files", "usr", "bin", "hello"),
                "directory": "usr/bin",
            },
            {
                "kind": "remote",
                "url": os.path.join(file_url, "dev-files", "usr", "include", "pony.h"),
                "directory": "usr/include",
            },
            {"kind": "patch", "path": "files/hello-patch.diff"},
        ],
    }
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    res = cli.run(project=project_dir, args=["source", "track", element_name])
    res.assert_success()

    res = cli.run(project=project_dir, args=["build", element_name])
    res.assert_success()

    # Should have one source ref
    patch_protos = os.path.join(project_dir, "cache", "source_protos", "patch")
    assert len(os.listdir(patch_protos)) == 1

    # modify hello-patch file and check tracking updates refs
    with open(os.path.join(file_path, "dev-files", "usr", "include", "pony.h"), "a") as f:
        f.write("\nappending nonsense")

    res = cli.run(project=project_dir, args=["source", "track", element_name])
    res.assert_success()
    assert "Found new revision: " in res.stderr

    res = cli.run(project=project_dir, args=["source", "fetch", element_name])
    res.assert_success()

    # We should have a new source ref
    assert len(os.listdir(patch_protos)) == 2
