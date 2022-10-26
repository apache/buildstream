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
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream._project import Project

from buildstream._testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils import dummy_context
from tests.testutils.element_generators import create_element_size


DATA_DIR = os.path.dirname(os.path.realpath(__file__))


# walk that removes the root directory from roots
def relative_walk(rootdir):
    for root, dirnames, filenames in os.walk(rootdir):
        relative_root = root.split(rootdir)[1]
        yield (relative_root, dirnames, filenames)


@pytest.mark.datafiles(DATA_DIR)
def test_source_staged(tmpdir, cli, datafiles):
    project_dir = os.path.join(datafiles.dirname, datafiles.basename, "project")
    cachedir = os.path.join(str(tmpdir), "cache")

    cli.configure({"cachedir": cachedir})

    res = cli.run(project=project_dir, args=["build", "import-bin.bst"])
    res.assert_success()

    with dummy_context() as context:
        context.cachedir = cachedir
        # load project and sourcecache
        project = Project(project_dir, context)
        project.ensure_fully_loaded()
        sourcecache = context.sourcecache
        cas = context.get_cascache()

        # now check that the source is in the refs file, this is pretty messy but
        # seems to be the only way to get the sources?
        element = project.load_elements(["import-bin.bst"])[0]
        element._query_source_cache()
        source = list(element.sources())[0]
        assert element._cached_sources()
        assert sourcecache.contains(source)

        # Extract the file and check it's the same as the one we imported
        digest = sourcecache.export(source)._get_digest()
        extractdir = os.path.join(str(tmpdir), "extract")
        cas.checkout(extractdir, digest)
        dir1 = extractdir
        dir2 = os.path.join(project_dir, "files", "bin-files")

        assert list(relative_walk(dir1)) == list(relative_walk(dir2))


# Check sources are staged during a fetch
@pytest.mark.datafiles(DATA_DIR)
def test_source_fetch(tmpdir, cli, datafiles):
    project_dir = os.path.join(datafiles.dirname, datafiles.basename, "project")
    cachedir = os.path.join(str(tmpdir), "cache")

    cli.configure({"cachedir": cachedir})

    res = cli.run(project=project_dir, args=["source", "fetch", "import-dev.bst"])
    res.assert_success()

    with dummy_context() as context:
        context.cachedir = cachedir
        # load project and sourcecache
        project = Project(project_dir, context)
        project.ensure_fully_loaded()
        cas = context.get_cascache()
        sourcecache = context.sourcecache

        element = project.load_elements(["import-dev.bst"])[0]
        element._query_source_cache()
        source = list(element.sources())[0]
        assert element._cached_sources()

        # check that the directory structures are identical
        digest = sourcecache.export(source)._get_digest()
        extractdir = os.path.join(str(tmpdir), "extract")
        cas.checkout(extractdir, digest)
        dir1 = extractdir
        dir2 = os.path.join(project_dir, "files", "dev-files")

        assert list(relative_walk(dir1)) == list(relative_walk(dir2))


# Check that with sources only in the CAS build successfully completes
@pytest.mark.datafiles(DATA_DIR)
def test_staged_source_build(tmpdir, datafiles, cli):
    project_dir = os.path.join(datafiles.dirname, datafiles.basename, "project")
    cachedir = os.path.join(str(tmpdir), "cache")
    element_path = "elements"
    source_protos = os.path.join(str(tmpdir), "cache", "source_protos")
    elementsources = os.path.join(str(tmpdir), "cache", "elementsources")
    source_dir = os.path.join(str(tmpdir), "cache", "sources")

    cli.configure({"cachedir": cachedir})

    create_element_size("target.bst", project_dir, element_path, [], 10000)

    with dummy_context() as context:
        context.cachedir = cachedir
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        element = project.load_elements(["import-dev.bst"])[0]

        # check consistency of the source
        element._query_source_cache()
        assert not element._cached_sources()

    res = cli.run(project=project_dir, args=["build", "target.bst"])
    res.assert_success()

    # delete artifacts check state is buildable
    cli.remove_artifact_from_cache(project_dir, "target.bst")
    states = cli.get_element_states(project_dir, ["target.bst"])
    assert states["target.bst"] == "buildable"

    # delete source dir and check that state is still buildable
    shutil.rmtree(source_dir)
    states = cli.get_element_states(project_dir, ["target.bst"])
    assert states["target.bst"] == "buildable"

    # build and check that no fetching was done.
    res = cli.run(project=project_dir, args=["build", "target.bst"])
    res.assert_success()
    assert "Fetching" not in res.stderr

    # assert the source directory is still empty (though there may be
    # directories from staging etc.)
    files = []
    for _, _, filename in os.walk(source_dir):
        files.extend(filename)
    assert not files, files

    # Now remove the source refs and check the state
    shutil.rmtree(source_protos)
    shutil.rmtree(elementsources)
    cli.remove_artifact_from_cache(project_dir, "target.bst")
    states = cli.get_element_states(project_dir, ["target.bst"])
    assert states["target.bst"] == "fetch needed"

    # Check that it now fetches from when building the target
    res = cli.run(project=project_dir, args=["build", "target.bst"])
    res.assert_success()
    assert "Fetching" in res.stderr
