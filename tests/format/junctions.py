# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "junctions",)


def update_project(project_path, updated_configuration):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf.update(updated_configuration)

    _yaml.roundtrip_dump(project_conf, project_conf_path)


#
# Test behavior of `bst show` on a junction element
#
@pytest.mark.datafiles(DATA_DIR)
def test_simple_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "simple")
    assert cli.get_element_state(project, "subproject.bst") == "junction"


#
# Test that we can build build a pipeline with a junction
#
@pytest.mark.datafiles(DATA_DIR)
def test_simple_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "simple")

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file from the subproject
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


#
# Test failure when there is a missing project.conf
#
@pytest.mark.datafiles(DATA_DIR)
def test_junction_missing_project_conf(cli, datafiles):
    project = os.path.join(str(datafiles), "simple")

    # Just remove the project.conf from the simple test and assert the error
    os.remove(os.path.join(project, "subproject", "project.conf"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)
    assert "target.bst [line 4 column 2]" in result.stderr


#
# Test failure when there is a missing project.conf in a workspaced junction
#
@pytest.mark.datafiles(DATA_DIR)
def test_workspaced_junction_missing_project_conf(cli, datafiles):
    project = os.path.join(str(datafiles), "simple")

    workspace_dir = os.path.join(project, "workspace")

    result = cli.run(project=project, args=["workspace", "open", "subproject.bst", "--directory", workspace_dir])
    result.assert_success()

    # Remove the project.conf from the workspace directory
    os.remove(os.path.join(workspace_dir, "project.conf"))

    # Assert the same missing project.conf error
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "target.bst [line 4 column 2]" in result.stderr


#
# Test successful builds of deeply nested targets
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,expected",
    [("target.bst", ["sub.txt", "subsub.txt"]), ("deeptarget.bst", ["sub.txt", "subsub.txt", "subsubsub.txt"]),],
    ids=["simple", "deep"],
)
def test_nested(cli, tmpdir, datafiles, target, expected):
    project = os.path.join(str(datafiles), "nested")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from all subprojects
    for filename in expected:
        assert os.path.exists(os.path.join(checkoutdir, filename))


#
# Test missing elements/junctions in subprojects
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,provenance",
    [
        ("target.bst", "target.bst [line 4 column 2]"),
        ("sub-target.bst", "junction-A.bst:target.bst [line 4 column 2]"),
        ("bad-junction.bst", "bad-junction.bst [line 3 column 2]"),
        ("sub-target-bad-junction.bst", "junction-A.bst:bad-junction-target.bst [line 4 column 2]"),
    ],
    ids=["subproject-target", "subsubproject-target", "local-junction", "subproject-junction"],
)
def test_missing_files(cli, datafiles, target, provenance):
    project = os.path.join(str(datafiles), "missing-element")
    result = cli.run(project=project, args=["show", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert provenance in result.stderr


#
# Test various invalid junction configuraions
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,domain,reason,provenance",
    [
        # Test a junction which itself has dependencies
        (
            "junction-with-deps.bst",
            ErrorDomain.LOAD,
            LoadErrorReason.INVALID_JUNCTION,
            "base-with-deps.bst [line 6 column 2]",
        ),
        # Test having a dependency directly on a junction
        ("junction-dep.bst", ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA, "junction-dep.bst [line 3 column 2]"),
        # Test that we error correctly when we junction-depend on a non-junction
        (
            "junctiondep-not-a-junction.bst",
            ErrorDomain.LOAD,
            LoadErrorReason.INVALID_DATA,
            "junctiondep-not-a-junction.bst [line 3 column 2]",
        ),
        # Test that overriding a subproject junction with the junction
        # declaring the override itself will result in an error
        (
            "target-self-override.bst",
            ErrorDomain.ELEMENT,
            "override-junction-with-self",
            "subproject-self-override.bst [line 16 column 20]",
        ),
    ],
    ids=["junction-with-deps", "deps-on-junction", "use-element-as-junction", "override-with-self"],
)
def test_invalid(cli, datafiles, target, domain, reason, provenance):
    project = os.path.join(str(datafiles), "invalid")
    result = cli.run(project=project, args=["build", target])
    result.assert_main_error(domain, reason)
    assert provenance in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,expect_exists,expect_not_exists",
    [("target-default.bst", "pony.txt", "horsy.txt"), ("target-explicit.bst", "horsy.txt", "pony.txt"),],
    ids=["check-values", "set-explicit-values"],
)
def test_options(cli, tmpdir, datafiles, target, expect_exists, expect_not_exists):
    project = os.path.join(str(datafiles), "options")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    assert os.path.exists(os.path.join(checkoutdir, expect_exists))
    assert not os.path.exists(os.path.join(checkoutdir, expect_not_exists))


#
# Test propagation of options through a junction
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "animal,expect_exists,expect_not_exists",
    [("pony", "pony.txt", "horsy.txt"), ("horsy", "horsy.txt", "pony.txt"),],
    ids=["pony", "horsy"],
)
def test_options_propagate(cli, tmpdir, datafiles, animal, expect_exists, expect_not_exists):
    project = os.path.join(str(datafiles), "options")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    update_project(
        project,
        {
            "options": {
                "animal": {
                    "type": "enum",
                    "description": "The kind of animal",
                    "values": ["pony", "horsy"],
                    "default": "pony",
                    "variable": "animal",
                }
            }
        },
    )

    # Build, checkout
    result = cli.run(project=project, args=["--option", "animal", animal, "build", "target-propagate.bst"])
    result.assert_success()
    result = cli.run(
        project=project,
        args=[
            "--option",
            "animal",
            animal,
            "artifact",
            "checkout",
            "target-propagate.bst",
            "--directory",
            checkoutdir,
        ],
    )
    result.assert_success()

    assert os.path.exists(os.path.join(checkoutdir, expect_exists))
    assert not os.path.exists(os.path.join(checkoutdir, expect_not_exists))


#
# A lot of testing is using local sources for the junctions for
# speed and convenience, however there are some internal optimizations
# for local sources, so we need to test some things using a real
# source which involves triggering fetches.
#
# We use the tar source for this since it is a core plugin.
#
@pytest.mark.datafiles(DATA_DIR)
def test_tar_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "use-repo")

    # Create the repo from 'baserepo' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Check that bst show succeeds with implicit subproject fetching and the
    # pipeline includes the subproject element
    element_list = cli.get_pipeline(project, ["target.bst"])
    assert "base.bst:target.bst" in element_list


@pytest.mark.datafiles(DATA_DIR)
def test_tar_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "use-repo")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'baserepo' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file from the subproject
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


@pytest.mark.datafiles(DATA_DIR)
def test_tar_missing_project_conf(cli, tmpdir, datafiles):
    project = datafiles / "use-repo"

    # Remove the project.conf from this repo
    os.remove(datafiles / "use-repo" / "baserepo" / "project.conf")

    # Create the repo from 'base' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, str(project / "base.bst"))

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_JUNCTION)

    # Assert that we have the expected provenance encoded into the error
    assert "target.bst [line 3 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_build_tar_cross_junction_names(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "use-repo")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(os.path.join(project, "baserepo"))

    # Write out junction element with tar source
    element = {"kind": "junction", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(project, "base.bst"))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=["build", "base.bst:target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "base.bst:target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert os.path.exists(os.path.join(checkoutdir, "base.txt"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target",
    [
        "junction-full-path.bst",
        "element-full-path.bst",
        "subproject.bst:subsubproject.bst:subsubsubproject.bst:target.bst",
    ],
    ids=["junction", "element", "command-line"],
)
def test_full_path(cli, tmpdir, datafiles, target):
    project = os.path.join(str(datafiles), "full-path")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file from base
    assert os.path.exists(os.path.join(checkoutdir, "subsubsub.txt"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,provenance",
    [
        ("junction-full-path-notfound.bst", "junction-full-path-notfound.bst [line 3 column 2]"),
        ("element-full-path-notfound.bst", "element-full-path-notfound.bst [line 3 column 2]"),
        ("subproject.bst:subsubproject.bst:pony.bst", None),
    ],
    ids=["junction", "element", "command-line"],
)
def test_full_path_not_found(cli, tmpdir, datafiles, target, provenance):
    project = os.path.join(str(datafiles), "full-path")

    # Build
    result = cli.run(project=project, args=["build", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Check that provenance was provided if expected
    if provenance:
        assert provenance in result.stderr


#
# Test the overrides feature.
#
# Here we reuse the `nested` project since it already has deep
# nesting, and add to it a couple of additional junctions to
# test overriding of junctions at various depts
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,expected",
    [
        # Test that we can override a subproject junction of a subproject
        ("target-overridden-subsubproject.bst", "subsubsub.txt"),
        # Test that we can override a subproject junction of a subproject's subproject
        ("target-overridden-subsubsubproject.bst", "surprise.txt"),
        # Test that we can override a subproject junction with a deep subproject path
        ("target-overridden-with-deepsubproject.bst", "deepsurprise.txt"),
    ],
    ids=["override-subproject", "override-subsubproject", "override-subproject-with-subsubproject"],
)
def test_overrides(cli, tmpdir, datafiles, target, expected):
    project = os.path.join(str(datafiles), "overrides")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    assert os.path.exists(os.path.join(checkoutdir, expected))


# Tests a situation where the same deep subproject is overridden
# more than once.
#
@pytest.mark.datafiles(DATA_DIR)
def test_override_twice(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "override-twice")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    assert os.path.exists(os.path.join(checkoutdir, "overridden-again.txt"))


#
# Test conflicting junction scenarios
#
# Note here we assert 2 provenances, we want to ensure that both
# provenances leading up to the use of a project are accounted for
# in a conflicting junction error.
#
# The second provenance can be None, because there will be no
# provenance for the originally loaded project if it was the toplevel
# project, or in some cases when a full path to a deep element was
# specified directly on the command line.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir,target,provenances",
    [
        # Test a stack element which depends directly on the same project twice
        (
            "conflicts",
            "simple-conflict.bst",
            ["simple-conflict.bst [line 5 column 2]", "simple-conflict.bst [line 4 column 2]"],
        ),
        # Test a dependency chain leading deep into a project which conflicts with the toplevel
        (
            "conflicts",
            "nested-conflict-toplevel.bst",
            ["subproject.bst:subsubproject-conflict-target.bst [line 4 column 2]"],
        ),
        # Test an attempt to override a subproject with a subproject of that same subproject through a different junction
        (
            "conflicts",
            "override-conflict.bst",
            [
                "subproject-override-conflicting-path.bst [line 13 column 23]",
                "override-conflict.bst [line 8 column 2]",
            ],
        ),
        # Same test as above, but specifying the target as a full path instead of a stack element
        (
            "conflicts",
            "subproject-override-conflicting-path.bst:subsubproject.bst:target.bst",
            ["subproject-override-conflicting-path.bst [line 13 column 23]"],
        ),
        # Test a dependency on a subproject conflicting with an include of a file from a different
        # version of the same project
        (
            "conflicts",
            "include-conflict-target.bst",
            ["include-conflict-target.bst [line 5 column 2]", "include-conflict.bst [line 4 column 7]"],
        ),
        # Test an element kind which needs to load it's plugin from a subproject, but
        # the element has a dependency on an element from a different version of the same project
        (
            "conflicts",
            "plugin-conflict.bst",
            ["project.conf [line 4 column 2]", "plugin-conflict.bst [line 4 column 2]"],
        ),
        # Test a project which subproject's the same project twice, but only lists it
        # as a duplicate via one of it's junctions.
        (
            "duplicates-simple-incomplete",
            "target.bst",
            ["target.bst [line 4 column 2]", "target.bst [line 5 column 2]"],
        ),
        # Test a project which subproject's the same project twice, but only lists it
        # as a duplicate via one of it's junctions.
        (
            "duplicates-nested-incomplete",
            "target.bst",
            ["target.bst [line 6 column 2]", "target.bst [line 4 column 2]", "target.bst [line 5 column 2]"],
        ),
        # Test a project which uses an internal subsubproject, but also uses that same subsubproject twice
        # at the toplevel, this test ensures we also get the provenance of the internal project in the error.
        (
            "internal-and-conflict",
            "target.bst",
            [
                "subproject.bst:subtarget.bst [line 10 column 2]",
                "target.bst [line 5 column 2]",
                "target.bst [line 6 column 2]",
            ],
        ),
    ],
    ids=[
        "simple",
        "nested",
        "override",
        "override-full-path",
        "include",
        "plugin",
        "incomplete-duplicates",
        "incomplete-nested-duplicates",
        "internal",
    ],
)
def test_conflict(cli, tmpdir, datafiles, project_dir, target, provenances):
    project = os.path.join(str(datafiles), project_dir)

    # Special case setup the conflicting project.conf
    if target == "plugin-conflict.bst":
        update_project(
            project, {"plugins": [{"origin": "junction", "junction": "subproject2.bst", "elements": ["found"],}]},
        )

    result = cli.run(project=project, args=["build", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CONFLICTING_JUNCTION)

    # Assert expected provenances
    for provenance in provenances:
        assert provenance in result.stderr


#
# Test circular references in junction override cycles
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,provenance1,provenance2",
    [
        # Override a subprojects subsubproject, with a subproject of the
        # subsubproject being overridden.
        (
            "target-overridden-subsubproject-circular.bst",
            "subproject-overriden-with-circular-reference.bst [line 8 column 23]",
            None,
        ),
        (
            "target-overridden-subsubproject-circular-link.bst",
            "link-subsubsubproject.bst [line 4 column 10]",
            "target-overridden-subsubproject-circular-link.bst [line 4 column 2]",
        ),
    ],
    ids=["override-self", "override-self-using-link"],
)
def test_circular_reference(cli, tmpdir, datafiles, target, provenance1, provenance2):
    project = os.path.join(str(datafiles), "circular-references")
    result = cli.run(project=project, args=["build", target])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CIRCULAR_REFERENCE)
    assert provenance1 in result.stderr
    if provenance2:
        assert provenance2 in result.stderr


#
# Test explicitly marked duplicates
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir",
    [
        # Test a project with two direct dependencies on the same project
        ("duplicates-simple"),
        # Test a project with a dependency on a project with two duplicate subprojects,
        # while additionally adding a dependency on that duplicated subproject at the toplevel
        ("duplicates-nested"),
        # Same as previous test, but duplicate the subprojects only from the toplevel,
        # ensuring that the pathing and addressing of elements works.
        ("duplicates-nested-full-path"),
        # Test a project with two direct dependencies on the same project, one of them
        # referred to via a link to the junction.
        ("duplicates-simple-link"),
        # Test a project where the toplevel duplicates a link in a subproject
        ("duplicates-nested-link1"),
        # Test a project where the toplevel duplicates a link to a nested subproject
        ("duplicates-nested-link2"),
        # Test a project which overrides the a subsubproject which is marked as a duplicate by the subproject,
        # ensure that the duplicate relationship for the subproject/subsubproject is preserved.
        ("duplicates-override-dup"),
        # Test a project which overrides a deep subproject multiple times in the hierarchy, the intermediate
        # junction to the deep subproject (which is overridden by the toplevel) marks that deep subproject as
        # a duplicate using a link element in the project.conf to mark the duplicate, this link is otherwise unused.
        ("duplicates-override-twice-link"),
    ],
    ids=[
        "simple",
        "nested",
        "nested-full-path",
        "simple-link",
        "link-in-subproject",
        "link-to-subproject",
        "overridden",
        "overridden-twice-link",
    ],
)
def test_duplicates(cli, tmpdir, datafiles, project_dir):
    project = os.path.join(str(datafiles), project_dir)

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()


#
# Test errors which occur when duplicate lists refer to elements which
# don't exist.
#
# While subprojects are not loaded by virtue of searching the duplicate
# lists, we do attempt to load elements in loaded projects in order to
# ensure that we properly traverse `link` elements.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir,provenance",
    [
        # Test a not found duplicate at the toplevel
        ("duplicates-simple-not-found", "project.conf [line 8 column 6]"),
        # Test a listed duplicate of a broken `link` target in a subproject
        ("duplicates-nested-not-found", "subproject.bst:subproject1-link.bst [line 4 column 10]"),
    ],
    ids=["simple", "broken-nested-link"],
)
def test_duplicates_not_found(cli, tmpdir, datafiles, project_dir, provenance):
    project = os.path.join(str(datafiles), project_dir)

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Check that provenance was provided if expected
    assert provenance in result.stderr


#
# Test internal projects
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project_dir,expected_files",
    [
        # Test a project which repeats a subproject which is also
        # internal to another subproject.
        ("internal-simple", ["subsub.txt", "subsub-again.txt"]),
        # Test a project which repeats a subproject which is also
        # internal to two other subprojects.
        ("internal-double", ["subsub1.txt", "subsub2.txt", "subsub-again.txt"]),
        # Test a project which repeats a subproject which is also
        # internal to another subproject, which marks it internal using a link.
        ("internal-link", ["subsub.txt", "subsub-again.txt"]),
        # Test a project which repeats a subproject which is also internal to another
        # subproject, and also overrides that same internal subproject.
        ("internal-override", ["subsub-override.txt", "subsub-again.txt"]),
    ],
    ids=["simple", "double", "link", "override"],
)
def test_internal(cli, tmpdir, datafiles, project_dir, expected_files):
    project = os.path.join(str(datafiles), project_dir)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected file
    for expected in expected_files:
        assert os.path.exists(os.path.join(checkoutdir, expected))
