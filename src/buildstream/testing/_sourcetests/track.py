#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain
from .._utils import generate_junction
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import update_project_configuration
from .utils import kind  # pylint: disable=unused-import


# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def generate_element(repo, element_path, dep_name=None):
    element = {"kind": "import", "sources": [repo.source_config()]}
    if dep_name:
        element["depends"] = [dep_name]

    _yaml.roundtrip_dump(element, element_path)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
def test_track(cli, tmpdir, datafiles, ref_storage, kind):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_name = "track-test-{}.bst".format(kind)

    update_project_configuration(project, {"ref-storage": ref_storage})

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    repo.create(dev_files_path)

    # Generate the element
    generate_element(repo, os.path.join(element_path, element_name))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == "no reference"

    # Now first try to track it
    result = cli.run(project=project, args=["source", "track", element_name])
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=["source", "fetch", element_name])
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == "buildable"

    # Assert there was a project.refs created, depending on the configuration
    if ref_storage == "project.refs":
        assert os.path.exists(os.path.join(project, "project.refs"))
    else:
        assert not os.path.exists(os.path.join(project, "project.refs"))


# NOTE:
#
#    This test checks that recursive tracking works by observing
#    element states after running a recursive tracking operation.
#
#    However, this test is ALSO valuable as it stresses the source
#    plugins in a situation where many source plugins are operating
#    at once on the same backing repository.
#
#    Do not change this test to use a separate 'Repo' per element
#    as that would defeat the purpose of the stress test, otherwise
#    please refactor that aspect into another test.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("amount", [1, 10])
def test_track_recurse(cli, tmpdir, datafiles, kind, amount):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")

    # Try to actually launch as many fetch jobs as possible at the same time
    #
    # This stresses the Source plugins and helps to ensure that
    # they handle concurrent access to the store correctly.
    cli.configure({"scheduler": {"fetchers": amount,}})

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    repo.create(dev_files_path)

    # Write out our test targets
    element_names = []
    last_element_name = None
    for i in range(amount + 1):
        element_name = "track-test-{}-{}.bst".format(kind, i + 1)
        filename = os.path.join(element_path, element_name)

        element_names.append(element_name)

        generate_element(repo, filename, dep_name=last_element_name)
        last_element_name = element_name

    # Assert that a fetch is needed
    states = cli.get_element_states(project, [last_element_name])
    for element_name in element_names:
        assert states[element_name] == "no reference"

    # Now first try to track it
    result = cli.run(project=project, args=["source", "track", "--deps", "all", last_element_name])
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=["source", "fetch", "--deps", "all", last_element_name])
    result.assert_success()

    # Assert that the base is buildable and the rest are waiting
    states = cli.get_element_states(project, [last_element_name])
    for element_name in element_names:
        if element_name == element_names[0]:
            assert states[element_name] == "buildable"
        else:
            assert states[element_name] == "waiting"


@pytest.mark.datafiles(DATA_DIR)
def test_track_recurse_except(cli, tmpdir, datafiles, kind):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_dep_name = "track-test-dep-{}.bst".format(kind)
    element_target_name = "track-test-target-{}.bst".format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    repo.create(dev_files_path)

    # Write out our test targets
    generate_element(repo, os.path.join(element_path, element_dep_name))
    generate_element(repo, os.path.join(element_path, element_target_name), dep_name=element_dep_name)

    # Assert that a fetch is needed
    states = cli.get_element_states(project, [element_target_name])
    assert states[element_dep_name] == "no reference"
    assert states[element_target_name] == "no reference"

    # Now first try to track it
    result = cli.run(
        project=project, args=["source", "track", "--deps", "all", "--except", element_dep_name, element_target_name]
    )
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=["source", "fetch", "--deps", "none", element_target_name])
    result.assert_success()

    # Assert that the dependency is buildable and the target is waiting
    states = cli.get_element_states(project, [element_target_name])
    assert states[element_dep_name] == "no reference"
    assert states[element_target_name] == "waiting"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
def test_cross_junction(cli, tmpdir, datafiles, ref_storage, kind):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")
    etc_files = os.path.join(subproject_path, "files", "etc-files")
    repo_element_path = os.path.join(subproject_path, "elements", "import-etc-repo.bst")

    update_project_configuration(project, {"ref-storage": ref_storage})

    repo = create_repo(kind, str(tmpdir.join("element_repo")))
    repo.create(etc_files)

    generate_element(repo, repo_element_path)

    generate_junction(str(tmpdir.join("junction_repo")), subproject_path, junction_path, store_ref=False)

    # Track the junction itself first.
    result = cli.run(project=project, args=["source", "track", "junction.bst"])
    result.assert_success()

    assert cli.get_element_state(project, "junction.bst:import-etc-repo.bst") == "no reference"

    # Track the cross junction element. -J is not given, it is implied.
    result = cli.run(project=project, args=["source", "track", "junction.bst:import-etc-repo.bst"])

    if ref_storage == "inline":
        # This is not allowed to track cross junction without project.refs.
        result.assert_main_error(ErrorDomain.PIPELINE, "untrackable-sources")
    else:
        result.assert_success()

        assert cli.get_element_state(project, "junction.bst:import-etc-repo.bst") == "buildable"

        assert os.path.exists(os.path.join(project, "project.refs"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
def test_track_include(cli, tmpdir, datafiles, ref_storage, kind):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_name = "track-test-{}.bst".format(kind)

    update_project_configuration(project, {"ref-storage": ref_storage})

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    # Generate the element
    element = {"kind": "import", "(@)": ["elements/sources.yml"]}
    sources = {"sources": [repo.source_config()]}

    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))
    _yaml.roundtrip_dump(sources, os.path.join(element_path, "sources.yml"))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == "no reference"

    # Now first try to track it
    result = cli.run(project=project, args=["source", "track", element_name])
    result.assert_success()

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=["source", "fetch", element_name])
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == "buildable"

    # Assert there was a project.refs created, depending on the configuration
    if ref_storage == "project.refs":
        assert os.path.exists(os.path.join(project, "project.refs"))
    else:
        assert not os.path.exists(os.path.join(project, "project.refs"))

        new_sources = _yaml.load(os.path.join(element_path, "sources.yml"), shortname="sources.yml")

        # Get all of the sources
        assert "sources" in new_sources
        sources_list = new_sources.get_sequence("sources")
        assert len(sources_list) == 1

        # Get the first source from the sources list
        new_source = sources_list.mapping_at(0)
        assert "ref" in new_source
        assert ref == new_source.get_str("ref")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
def test_track_include_junction(cli, tmpdir, datafiles, ref_storage, kind):
    project = str(datafiles)
    dev_files_path = os.path.join(project, "files", "dev-files")
    element_path = os.path.join(project, "elements")
    element_name = "track-test-{}.bst".format(kind)
    subproject_path = os.path.join(project, "files", "sub-project")
    sub_element_path = os.path.join(subproject_path, "elements")
    junction_path = os.path.join(element_path, "junction.bst")

    update_project_configuration(project, {"ref-storage": ref_storage})

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir.join("element_repo")))
    repo.create(dev_files_path)

    # Generate the element
    element = {"kind": "import", "(@)": ["junction.bst:elements/sources.yml"]}
    sources = {"sources": [repo.source_config()]}

    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))
    _yaml.roundtrip_dump(sources, os.path.join(sub_element_path, "sources.yml"))

    generate_junction(str(tmpdir.join("junction_repo")), subproject_path, junction_path, store_ref=True)

    result = cli.run(project=project, args=["source", "track", "junction.bst"])
    result.assert_success()

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == "no reference"

    # Now first try to track it
    result = cli.run(project=project, args=["source", "track", element_name])

    # Assert there was a project.refs created, depending on the configuration
    if ref_storage == "inline":
        # FIXME: We should expect an error. But only a warning is emitted
        # result.assert_main_error(ErrorDomain.SOURCE, 'tracking-junction-fragment')

        assert "junction.bst:elements/sources.yml: Cannot track source in a fragment from a junction" in result.stderr
    else:
        assert os.path.exists(os.path.join(project, "project.refs"))

        # And now fetch it: The Source has probably already cached the
        # latest ref locally, but it is not required to have cached
        # the associated content of the latest ref at track time, that
        # is the job of fetch.
        result = cli.run(project=project, args=["source", "fetch", element_name])
        result.assert_success()

        # Assert that we are now buildable because the source is
        # now cached.
        assert cli.get_element_state(project, element_name) == "buildable"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
def test_track_junction_included(cli, tmpdir, datafiles, ref_storage, kind):
    project = str(datafiles)
    element_path = os.path.join(project, "elements")
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(element_path, "junction.bst")

    update_project_configuration(project, {"ref-storage": ref_storage, "(@)": ["junction.bst:test.yml"]})

    generate_junction(str(tmpdir.join("junction_repo")), subproject_path, junction_path, store_ref=False)

    result = cli.run(project=project, args=["source", "track", "junction.bst"])
    result.assert_success()
