# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo
from buildstream.testing._utils.site import HAVE_GIT


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "junctions",)


def copy_subprojects(project, datafiles, subprojects):
    for subproject in subprojects:
        shutil.copytree(os.path.join(str(datafiles), subproject), os.path.join(str(project), subproject))


@pytest.mark.datafiles(DATA_DIR)
def test_simple_pipeline(cli, datafiles):
    project = os.path.join(str(datafiles), "foo")
    copy_subprojects(project, datafiles, ["base"])

    # Check that the pipeline includes the subproject element
    element_list = cli.get_pipeline(project, ["target.bst"])
    assert "base.bst:target.bst" in element_list


@pytest.mark.datafiles(DATA_DIR)
def test_simple_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "foo")
    copy_subprojects(project, datafiles, ["base"])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "foo.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_junction_missing_project_conf(cli, datafiles):
    project = datafiles / "foo"
    copy_subprojects(project, datafiles, ["base"])

    # TODO: see if datafiles can tidy this concat up

    os.remove(project / "base" / "project.conf")

    # Note that both 'foo' and 'base' projects have a 'target.bst'. The
    # 'app.bst' in 'foo' depends on the 'target.bst' in 'base', i.e.:
    #
    #   foo/base/target.bst
    #   foo/app.bst -> foo/base/target.bst
    #   foo/target.bst -> foo/app.bst, foor/base/target.bst
    #
    # In a previous bug (issue #960) if the 'project.conf' was not found in the
    # junction's dir then we were continuing the search in the parent dirs.
    #
    # This would mean that the dep on 'target.bst' would resolve to
    # 'foo/target.bst' instead of 'foo/base/target.bst'.
    #
    # That would lead to a 'circular dependency error' in this setup, when we
    # expect an 'invalid junction'.
    #
    result = cli.run(project=project, args=["build", "app.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "app.bst [line 6 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_workspaced_junction_missing_project_conf(cli, datafiles):
    # See test_junction_missing_project_conf for some more background.

    project = datafiles / "foo"
    workspace_dir = project / "base_workspace"
    copy_subprojects(project, datafiles, ["base"])

    result = cli.run(project=project, args=["workspace", "open", "base.bst", "--directory", workspace_dir])
    print(result)
    result.assert_success()

    os.remove(workspace_dir / "project.conf")

    result = cli.run(project=project, args=["build", "app.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "app.bst [line 6 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_build_of_same_junction_used_twice(cli, datafiles):
    project = os.path.join(str(datafiles), "inconsistent-names")

    # Check we can build a project that contains the same junction
    # that is used twice, but named differently
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_missing_file_in_subproject(cli, datafiles):
    project = os.path.join(str(datafiles), "missing-element")
    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "target.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_missing_file_in_subsubproject(cli, datafiles):
    project = os.path.join(str(datafiles), "missing-element")
    result = cli.run(project=project, args=["show", "sub-target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "junction-A.bst:target.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_missing_junction_in_subproject(cli, datafiles):
    project = os.path.join(str(datafiles), "missing-element")
    result = cli.run(project=project, args=["show", "sub-target-bad-junction.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "junction-A.bst:bad-junction-target.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_nested_simple(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "foo")
    copy_subprojects(project, datafiles, ["base"])

    project = os.path.join(str(datafiles), "nested")
    copy_subprojects(project, datafiles, ["foo"])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from all subprojects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "foo.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_nested_double(cli, tmpdir, datafiles):
    project_foo = os.path.join(str(datafiles), "foo")
    copy_subprojects(project_foo, datafiles, ["base"])

    project_bar = os.path.join(str(datafiles), "bar")
    copy_subprojects(project_bar, datafiles, ["base"])

    project = os.path.join(str(datafiles), "toplevel")
    copy_subprojects(project, datafiles, ["base", "foo", "bar"])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from all subprojects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "foo.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "bar.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_nested_conflict(cli, datafiles):
    project_foo = os.path.join(str(datafiles), "foo")
    copy_subprojects(project_foo, datafiles, ["base"])

    project_bar = os.path.join(str(datafiles), "bar")
    copy_subprojects(project_bar, datafiles, ["base"])

    project = os.path.join(str(datafiles), "conflict")
    copy_subprojects(project, datafiles, ["foo", "bar"])

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CONFLICTING_JUNCTION)

    assert "bar.bst:target.bst [line 3 column 2]" in result.stderr


# Test that we error correctly when the junction element itself is missing
@pytest.mark.datafiles(DATA_DIR)
def test_missing_junction(cli, datafiles):
    project = os.path.join(str(datafiles), "invalid")

    result = cli.run(project=project, args=["build", "missing.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


# Test that we error correctly when an element is not found in the subproject
@pytest.mark.datafiles(DATA_DIR)
def test_missing_subproject_element(cli, datafiles):
    project = os.path.join(str(datafiles), "invalid")
    copy_subprojects(project, datafiles, ["base"])

    result = cli.run(project=project, args=["build", "missing-element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


# Test that we error correctly when a junction itself has dependencies
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_with_deps(cli, datafiles):
    project = os.path.join(str(datafiles), "invalid")
    copy_subprojects(project, datafiles, ["base"])

    result = cli.run(project=project, args=["build", "junction-with-deps.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)


# Test that we error correctly when a junction is directly depended on
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_junction_dep(cli, datafiles):
    project = os.path.join(str(datafiles), "invalid")
    copy_subprojects(project, datafiles, ["base"])

    result = cli.run(project=project, args=["build", "junction-dep.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


# Test that we error correctly when we junction-depend on a non-junction
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_junctiondep_not_a_junction(cli, datafiles):
    project = os.path.join(str(datafiles), "invalid")
    copy_subprojects(project, datafiles, ["base"])

    result = cli.run(project=project, args=["build", "junctiondep-not-a-junction.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)

    # Assert that we have the expected provenance encoded into the error
    assert "junctiondep-not-a-junction.bst [line 3 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_options_default(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "options-default")
    copy_subprojects(project, datafiles, ["options-base"])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    assert os.path.exists(os.path.join(checkoutdir, "pony.txt"))
    assert not os.path.exists(os.path.join(checkoutdir, "horsy.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_options(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "options")
    copy_subprojects(project, datafiles, ["options-base"])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    assert not os.path.exists(os.path.join(checkoutdir, "pony.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "horsy.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_options_inherit(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "options-inherit")
    copy_subprojects(project, datafiles, ["options-base"])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    assert not os.path.exists(os.path.join(checkoutdir, "pony.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "horsy.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_git_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "foo")

    # Create the repo from 'base' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "base"))

    # Write out junction element with git source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Check that bst show succeeds with implicit subproject fetching and the
    # pipeline includes the subproject element
    element_list = cli.get_pipeline(project, ["target.bst"])
    assert "base.bst:target.bst" in element_list


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_git_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "foo")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "base"))

    # Write out junction element with git source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "foo.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_git_missing_project_conf(cli, tmpdir, datafiles):
    project = datafiles / "foo"

    # See test_junction_missing_project_conf for some more background.
    os.remove(datafiles / "base" / "project.conf")

    # Create the repo from 'base' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "base"))

    # Write out junction element with git source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, str(project / "base.bst"))

    result = cli.run(project=project, args=["build", "app.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "app.bst [line 6 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_cross_junction_names(cli, datafiles):
    project = os.path.join(str(datafiles), "foo")
    copy_subprojects(project, datafiles, ["base"])

    element_list = cli.get_pipeline(project, ["base.bst:target.bst"])
    assert "base.bst:target.bst" in element_list


@pytest.mark.datafiles(DATA_DIR)
def test_build_git_cross_junction_names(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "foo")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "base"))

    # Write out junction element with git source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    print(element)
    print(cli.get_pipeline(project, ["base.bst"]))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=["build", "base.bst:target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "base.bst:target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_config_target(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "config-target")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from sub-sub-project
    assert os.path.exists(os.path.join(checkoutdir, "hello.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_sources_and_target(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "config-target")

    result = cli.run(project=project, args=["show", "invalid-source-target.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, None)

    assert "junction elements cannot define both 'sources' and 'target' config option" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_target_name(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "config-target")

    # Rename our junction element to the same name as its target
    old_path = os.path.join(project, "elements/subsubproject.bst")
    new_path = os.path.join(project, "elements/subsubproject-junction.bst")
    os.rename(old_path, new_path)

    # This should fail now
    result = cli.run(project=project, args=["show", "subsubproject-junction.bst"])
    result.assert_main_error(ErrorDomain.ELEMENT, None)

    assert "junction elements cannot target an element with the same name" in result.stderr


# We cannot exhaustively test all possible ways in which this can go wrong, so
# test a couple of common ways in which we expect this to go wrong.
@pytest.mark.parametrize("target", ["no-junction.bst", "nested-junction-target.bst"])
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_target_format(cli, tmpdir, datafiles, target):
    project = os.path.join(str(datafiles), "config-target")

    result = cli.run(project=project, args=["show", target])
    result.assert_main_error(ErrorDomain.ELEMENT, None)

    assert "'target' option must be in format '{junction-name}:{element-name}'" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_junction_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "foo")
    copy_subprojects(project, datafiles, ["base"])

    # Show, assert that it says junction
    assert cli.get_element_state(project, "base.bst") == "junction"
