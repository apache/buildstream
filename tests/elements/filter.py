# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream.testing import create_repo
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain
from buildstream import _yaml

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "filter",)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_include(datafiles, cli, tmpdir):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "output-include.bst"])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "output-include.bst", "--directory", checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "foo"))
    assert not os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_include_dynamic(datafiles, cli, tmpdir):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "output-dynamic-include.bst"])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, "checkout")
    result = cli.run(
        project=project, args=["artifact", "checkout", "output-dynamic-include.bst", "--directory", checkout]
    )
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "foo"))
    assert not os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_exclude(datafiles, cli, tmpdir):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "output-exclude.bst"])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "output-exclude.bst", "--directory", checkout])
    result.assert_success()
    assert not os.path.exists(os.path.join(checkout, "foo"))
    assert os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_orphans(datafiles, cli, tmpdir):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "output-orphans.bst"])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "output-orphans.bst", "--directory", checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "baz"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_deps_ok(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "deps-permitted.bst"])
    result.assert_success()

    result = cli.run(project=project, args=["show", "--deps=run", "--format='%{name}'", "deps-permitted.bst"])
    result.assert_success()

    assert "output-exclude.bst" in result.output
    assert "output-orphans.bst" in result.output


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_forbid_sources(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "forbidden-source.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, "element-forbidden-sources")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_forbid_multi_bdep(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "forbidden-multi-bdep.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, "filter-bdepend-wrong-count")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_forbid_no_bdep(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "forbidden-no-bdep.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, "filter-bdepend-wrong-count")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_forbid_also_rdep(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "forbidden-also-rdep.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, "filter-bdepend-also-rdepend")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_workspace_open(datafiles, cli, tmpdir):
    project = str(datafiles)
    workspace_dir = os.path.join(tmpdir.dirname, tmpdir.basename, "workspace")
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace_dir, "deps-permitted.bst"])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace_dir, "foo"))
    assert os.path.exists(os.path.join(workspace_dir, "bar"))
    assert os.path.exists(os.path.join(workspace_dir, "baz"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_workspace_open_multi(datafiles, cli):
    project = str(datafiles)
    result = cli.run(
        cwd=project, project=project, args=["workspace", "open", "deps-permitted.bst", "output-orphans.bst"]
    )
    result.assert_success()
    assert os.path.exists(os.path.join(project, "input"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_workspace_build(datafiles, cli, tmpdir):
    project = str(datafiles)
    tempdir = os.path.join(tmpdir.dirname, tmpdir.basename)
    workspace_dir = os.path.join(tempdir, "workspace")
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace_dir, "output-orphans.bst"])
    result.assert_success()
    src = os.path.join(workspace_dir, "foo")
    dst = os.path.join(workspace_dir, "quux")
    shutil.copyfile(src, dst)
    result = cli.run(project=project, args=["build", "output-orphans.bst"])
    result.assert_success()
    checkout_dir = os.path.join(tempdir, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "output-orphans.bst", "--directory", checkout_dir])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout_dir, "quux"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_workspace_close(datafiles, cli, tmpdir):
    project = str(datafiles)
    tempdir = os.path.join(tmpdir.dirname, tmpdir.basename)
    workspace_dir = os.path.join(tempdir, "workspace")
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace_dir, "output-orphans.bst"])
    result.assert_success()
    src = os.path.join(workspace_dir, "foo")
    dst = os.path.join(workspace_dir, "quux")
    shutil.copyfile(src, dst)
    result = cli.run(project=project, args=["workspace", "close", "deps-permitted.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "output-orphans.bst"])
    result.assert_success()
    checkout_dir = os.path.join(tempdir, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "output-orphans.bst", "--directory", checkout_dir])
    result.assert_success()
    assert not os.path.exists(os.path.join(checkout_dir, "quux"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_workspace_reset(datafiles, cli, tmpdir):
    project = str(datafiles)
    tempdir = os.path.join(tmpdir.dirname, tmpdir.basename)
    workspace_dir = os.path.join(tempdir, "workspace")
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace_dir, "output-orphans.bst"])
    result.assert_success()
    src = os.path.join(workspace_dir, "foo")
    dst = os.path.join(workspace_dir, "quux")
    shutil.copyfile(src, dst)
    result = cli.run(project=project, args=["workspace", "reset", "deps-permitted.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "output-orphans.bst"])
    result.assert_success()
    checkout_dir = os.path.join(tempdir, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "output-orphans.bst", "--directory", checkout_dir])
    result.assert_success()
    assert not os.path.exists(os.path.join(checkout_dir, "quux"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_track(datafiles, cli, tmpdir):
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"

    project_config = {
        "name": "filter-track-test",
        "min-version": "2.0",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.roundtrip_dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.roundtrip_dump(input_config, input_file)

    filter1_config = {"kind": "filter", "depends": [{"filename": input_name, "type": "build"}]}
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.roundtrip_dump(filter1_config, filter1_file)

    filter2_config = {"kind": "filter", "depends": [{"filename": "filter1.bst", "type": "build"}]}
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.roundtrip_dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == "no reference"

    # Now try to track it
    result = cli.run(project=project, args=["source", "track", "filter2.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file, shortname=None)
    source_node = new_input.get_sequence("sources").mapping_at(0)
    new_input_ref = source_node.get_str("ref")
    assert new_input_ref == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_track_excepted(datafiles, cli, tmpdir):
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"

    project_config = {
        "name": "filter-track-test",
        "min-version": "2.0",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.roundtrip_dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.roundtrip_dump(input_config, input_file)

    filter1_config = {"kind": "filter", "depends": [{"filename": input_name, "type": "build"}]}
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.roundtrip_dump(filter1_config, filter1_file)

    filter2_config = {"kind": "filter", "depends": [{"filename": "filter1.bst", "type": "build"}]}
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.roundtrip_dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == "no reference"

    # Now try to track it
    result = cli.run(project=project, args=["source", "track", "filter2.bst", "--except", "input.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file, shortname=None)
    source_node = new_input.get_sequence("sources").mapping_at(0)
    assert "ref" not in source_node


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_track_multi_to_one(datafiles, cli, tmpdir):
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"

    project_config = {
        "name": "filter-track-test",
        "min-version": "2.0",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.roundtrip_dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.roundtrip_dump(input_config, input_file)

    filter1_config = {"kind": "filter", "depends": [{"filename": input_name, "type": "build"}]}
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.roundtrip_dump(filter1_config, filter1_file)

    filter2_config = {"kind": "filter", "depends": [{"filename": input_name, "type": "build"}]}
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.roundtrip_dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == "no reference"

    # Now try to track it
    result = cli.run(project=project, args=["source", "track", "filter1.bst", "filter2.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file, shortname=None)
    source_node = new_input.get_sequence("sources").mapping_at(0)
    new_ref = source_node.get_str("ref")
    assert new_ref == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_track_multi(datafiles, cli, tmpdir):
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"
    input2_name = "input2.bst"

    project_config = {
        "name": "filter-track-test",
        "min-version": "2.0",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.roundtrip_dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.roundtrip_dump(input_config, input_file)

    input2_config = dict(input_config)
    input2_file = os.path.join(elements_dir, input2_name)
    _yaml.roundtrip_dump(input2_config, input2_file)

    filter1_config = {"kind": "filter", "depends": [{"filename": input_name, "type": "build"}]}
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.roundtrip_dump(filter1_config, filter1_file)

    filter2_config = {"kind": "filter", "depends": [{"filename": input2_name, "type": "build"}]}
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.roundtrip_dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    states = cli.get_element_states(project, [input_name, input2_name])

    assert states == {
        input_name: "no reference",
        input2_name: "no reference",
    }

    # Now try to track it
    result = cli.run(project=project, args=["source", "track", "filter1.bst", "filter2.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file, shortname=None)
    source_node = new_input.get_sequence("sources").mapping_at(0)
    new_ref = source_node.get_str("ref")
    assert new_ref == ref

    new_input2 = _yaml.load(input2_file, shortname=None)
    source_node2 = new_input2.get_sequence("sources").mapping_at(0)
    new_ref2 = source_node2.get_str("ref")
    assert new_ref2 == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_track_multi_exclude(datafiles, cli, tmpdir):
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"
    input2_name = "input2.bst"

    project_config = {
        "name": "filter-track-test",
        "min-version": "2.0",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.roundtrip_dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.roundtrip_dump(input_config, input_file)

    input2_config = dict(input_config)
    input2_file = os.path.join(elements_dir, input2_name)
    _yaml.roundtrip_dump(input2_config, input2_file)

    filter1_config = {"kind": "filter", "depends": [{"filename": input_name, "type": "build"}]}
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.roundtrip_dump(filter1_config, filter1_file)

    filter2_config = {"kind": "filter", "depends": [{"filename": input2_name, "type": "build"}]}
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.roundtrip_dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    states = cli.get_element_states(project, [input_name, input2_name])
    assert states == {
        input_name: "no reference",
        input2_name: "no reference",
    }

    # Now try to track it
    result = cli.run(project=project, args=["source", "track", "filter1.bst", "filter2.bst", "--except", input_name])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file, shortname=None)
    source_node = new_input.get_sequence("sources").mapping_at(0)
    assert "ref" not in source_node

    new_input2 = _yaml.load(input2_file, shortname=None)
    source_node2 = new_input2.get_sequence("sources").mapping_at(0)
    new_ref2 = source_node2.get_str("ref")
    assert new_ref2 == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_include_with_indirect_deps(datafiles, cli, tmpdir):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "output-include-with-indirect-deps.bst"])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, "checkout")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", "output-include-with-indirect-deps.bst", "--directory", checkout],
    )
    result.assert_success()

    # direct dependencies should be staged and filtered
    assert os.path.exists(os.path.join(checkout, "baz"))

    # indirect dependencies shouldn't be staged and filtered
    assert not os.path.exists(os.path.join(checkout, "foo"))
    assert not os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_fails_for_nonexisting_domain(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, args=["build", "output-include-nonexistent-domain.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    error = "Unknown domains were used in output-include-nonexistent-domain.bst [line 7 column 2]"
    assert error in result.stderr
    assert "- unknown_file" in result.stderr


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_pass_integration(datafiles, cli):
    project = str(datafiles)

    # Explicitly not passing integration commands should be fine
    result = cli.run(project=project, args=["build", "no-pass-integration.bst"])
    result.assert_success()

    # Passing integration commands should build nicely
    result = cli.run(project=project, args=["build", "pass-integration.bst"])
    result.assert_success()

    # Checking out elements which don't pass integration commands should still work
    checkout_dir = os.path.join(project, "no-pass")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", "--integrate", "--directory", checkout_dir, "no-pass-integration.bst"],
    )
    result.assert_success()

    # Checking out the artifact should fail if we run integration commands, as
    # the staged artifacts don't have a shell
    checkout_dir = os.path.join(project, "pass")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", "--integrate", "--directory", checkout_dir, "pass-integration.bst"],
    )
    result.assert_main_error(ErrorDomain.STREAM, "missing-command")


@pytest.mark.datafiles(os.path.join(DATA_DIR, "basic"))
def test_filter_stack_depend_failure(datafiles, cli):
    project = str(datafiles)

    result = cli.run(project=project, args=["build", "forbidden-stack-dep.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, "filter-bdepend-no-artifact")
