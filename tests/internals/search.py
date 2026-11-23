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

from buildstream._project import Project
from buildstream._stream import Stream

from tests.testutils import dummy_context


@pytest.mark.parametrize(
    "pattern,name,expected",
    [
        # Full relative path
        ("components/glib.bst", "components/glib.bst", True),
        # Basename with and without extension
        ("glib.bst", "components/glib.bst", True),
        ("glib", "components/glib.bst", True),
        # Globs on the path and on the basename
        ("components/*", "components/glib.bst", True),
        ("gli*", "components/glib.bst", True),
        ("*.bst", "components/glib.bst", True),
        # Partial names are not matched without a glob
        ("gli", "components/glib.bst", False),
        ("components", "components/glib.bst", False),
        # Directory components are not matched by the basename
        ("components/glib", "components/glib.bst", False),
        # Matching is case sensitive
        ("GLIB", "components/glib.bst", False),
        # Unrelated names
        ("gtk", "components/glib.bst", False),
    ],
)
def test_search_match(pattern, name, expected):
    assert Stream._search_match(pattern, name) == expected


def write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


@pytest.fixture
def project_dir(tmpdir):
    basedir = str(tmpdir)
    write(os.path.join(basedir, "project.conf"), "name: test\nmin-version: 2.0\nelement-path: elements\n")

    elements = os.path.join(basedir, "elements")
    write(os.path.join(elements, "top.bst"))
    write(os.path.join(elements, "components", "glib.bst"))
    write(os.path.join(elements, "components", "notes.txt"))

    # Staged junctions and BuildStream internals are never listed
    write(os.path.join(elements, ".bst", "staged.bst"))

    # A nested project, such as the local source of a junction
    write(os.path.join(elements, "sub", "project.conf"), "name: sub\nmin-version: 2.0\n")
    write(os.path.join(elements, "sub", "inner.bst"))

    return basedir


@pytest.mark.parametrize(
    "skip_subprojects,expected",
    [
        (False, ["components/glib.bst", "sub/inner.bst", "top.bst"]),
        (True, ["components/glib.bst", "top.bst"]),
    ],
    ids=["all", "skip-subprojects"],
)
def test_list_element_files(project_dir, skip_subprojects, expected):
    with dummy_context() as context:
        project = Project(project_dir, context)
        files = project.list_element_files(skip_subprojects=skip_subprojects)
        assert sorted(files) == expected
