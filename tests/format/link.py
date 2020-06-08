# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os

import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.exceptions import ErrorDomain, LoadErrorReason


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "link",)

#
# Test links to elements, this tests both specifying the link as
# the main target, and also as a dependency of the main target.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", ["target.bst", "hello-link.bst"])
def test_simple_link(cli, tmpdir, datafiles, target):
    project = os.path.join(str(datafiles), "simple")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from sub-sub-project
    assert os.path.exists(os.path.join(checkoutdir, "hello.txt"))


#
# Test links to elements, this tests both specifying the link as
# the main target, and also as a dependency of the main target, while
# also using a conditional statement in the link
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target", ["target.bst", "target-link.bst"])
@pytest.mark.parametrize("greeting,expected_file", [("hello", "hello.txt"), ("goodbye", "goodbye.txt")])
def test_conditional_link(cli, tmpdir, datafiles, target, greeting, expected_file):
    project = os.path.join(str(datafiles), "conditional")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["-o", "greeting", greeting, "build", target])
    result.assert_success()
    result = cli.run(
        project=project, args=["-o", "greeting", greeting, "artifact", "checkout", target, "--directory", checkoutdir]
    )
    result.assert_success()

    # Check that the checkout contains the expected files from sub-sub-project
    assert os.path.exists(os.path.join(checkoutdir, expected_file))


#
# Test links to junctions from local projects and subprojects
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target", ["target-local.bst", "target-nested.bst", "full-path-link.bst", "target-full-path.bst"]
)
def test_simple_junctions(cli, tmpdir, datafiles, target):
    project = os.path.join(str(datafiles), "simple-junctions")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["build", target])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", target, "--directory", checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from sub-sub-project
    assert os.path.exists(os.path.join(checkoutdir, "hello.txt"))


#
# Test links which resolve junction targets conditionally
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("greeting,expected_file", [("hello", "hello.txt"), ("goodbye", "goodbye.txt")])
def test_conditional_junctions(cli, tmpdir, datafiles, greeting, expected_file):
    project = os.path.join(str(datafiles), "conditional-junctions")
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=["-o", "greeting", greeting, "build", "target.bst"])
    result.assert_success()
    result = cli.run(
        project=project,
        args=["-o", "greeting", greeting, "artifact", "checkout", "target.bst", "--directory", checkoutdir],
    )
    result.assert_success()

    # Check that the checkout contains the expected files from sub-sub-project
    assert os.path.exists(os.path.join(checkoutdir, expected_file))


#
# Tests links which refer to non-existing elements or junctions
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,provenance",
    [
        # Target is a link to a non-existing local element
        ("link-target.bst", "link-target.bst [line 4 column 10]"),
        # Target is a stack depending on a link to a non-existing local element
        ("depends-on-link-target.bst", "link-target.bst [line 4 column 10]",),
        # Depends on non-existing subproject element, via a local link
        ("linked-local-junction-target.bst", "linked-local-junction-target.bst [line 4 column 2]",),
        # Depends on non-existing subsubproject element, via a local link
        ("linked-nested-junction-target.bst", "linked-nested-junction-target.bst [line 4 column 2]",),
        # Depends on an element via a link to a non-existing local junction
        ("linked-local-junction.bst", "subproject-link-notfound.bst [line 4 column 10]",),
        # Depends on an element via a link to a non-existing subproject junction
        ("linked-nested-junction.bst", "subsubproject-link-notfound.bst [line 4 column 10]",),
        # Target is a link to a non-existing nested element referred to with a full path
        ("link-full-path.bst", "link-full-path.bst [line 4 column 10]"),
        # Target depends on a link to a non-existing nested element referred to with a full path
        ("target-full-path.bst", "link-full-path.bst [line 4 column 10]"),
    ],
)
def test_link_not_found(cli, tmpdir, datafiles, target, provenance):
    project = os.path.join(str(datafiles), "notfound")
    result = cli.run(project=project, args=["build", target])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)
    assert provenance in result.stderr


#
# Tests links with invalid configurations
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "target,expected_error,expected_reason",
    [
        # Test link which declares sources, either directly of via a dependency
        ("link-with-sources.bst", ErrorDomain.ELEMENT, "element-forbidden-sources"),
        ("target-link-with-sources.bst", ErrorDomain.ELEMENT, "element-forbidden-sources"),
        # Test link which declares dependencies, either directly of via a dependency
        ("link-with-dependencies.bst", ErrorDomain.LOAD, LoadErrorReason.LINK_FORBIDDEN_DEPENDENCIES),
    ],
)
def test_link_invalid_config(cli, tmpdir, datafiles, target, expected_error, expected_reason):
    project = os.path.join(str(datafiles), "invalid")
    result = cli.run(project=project, args=["show", target])
    result.assert_main_error(expected_error, expected_reason)
