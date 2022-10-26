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
from contextlib import contextmanager
import os
import pytest

from buildstream.exceptions import LoadErrorReason
from buildstream._exceptions import LoadError
from buildstream._project import Project
from buildstream._loader import LoadElement

from tests.testutils import dummy_context


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "loader",
)


@contextmanager
def make_loader(basedir):
    with dummy_context() as context:
        project = Project(basedir, context)
        yield project.loader


##############################################################
#  Basics: Test behavior loading the simplest of projects    #
##############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_one_file(datafiles):

    basedir = str(datafiles)
    with make_loader(basedir) as loader:
        element = loader.load(["elements/onefile.bst"])[0]

        assert isinstance(element, LoadElement)
        assert element.kind == "pony"


@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_missing_file(datafiles):

    basedir = str(datafiles)
    with make_loader(basedir) as loader, pytest.raises(LoadError) as exc:
        loader.load(["elements/missing.bst"])

    assert exc.value.reason == LoadErrorReason.MISSING_FILE


@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_invalid_reference(datafiles):

    basedir = str(datafiles)
    with make_loader(basedir) as loader, pytest.raises(LoadError) as exc:
        loader.load(["elements/badreference.bst"])

    assert exc.value.reason == LoadErrorReason.INVALID_YAML


@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_invalid_yaml(datafiles):

    basedir = str(datafiles)
    with make_loader(basedir) as loader, pytest.raises(LoadError) as exc:
        loader.load(["elements/badfile.bst"])

    assert exc.value.reason == LoadErrorReason.INVALID_YAML


@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_fail_fullpath_target(datafiles):

    basedir = str(datafiles)
    fullpath = os.path.join(basedir, "elements", "onefile.bst")

    with make_loader(basedir) as loader, pytest.raises(LoadError) as exc:
        loader.load([fullpath])

    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_invalid_key(datafiles):

    basedir = str(datafiles)
    with make_loader(basedir) as loader, pytest.raises(LoadError) as exc:
        loader.load(["elements/invalidkey.bst"])

    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR, "onefile"))
def test_invalid_directory_load(datafiles):

    basedir = str(datafiles)
    os.makedirs(os.path.join(basedir, "element.bst"))
    with make_loader(basedir) as loader, pytest.raises(LoadError) as exc:
        loader.load(["element.bst"])

    assert exc.value.reason == LoadErrorReason.LOADING_DIRECTORY
