# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml

from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing.integration import walk_dir
from buildstream.testing._utils.site import HAVE_SANDBOX, BUILDBOX_RUN


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def create_compose_element(name, path, config=None):
    if config is None:
        config = {}

    element = {
        "kind": "compose",
        "depends": [
            {"filename": "compose/amhello.bst", "type": "build"},
            {"filename": "compose/test.bst", "type": "build"},
        ],
        "config": config,
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "include_domains,exclude_domains,expected",
    [
        # Test flat inclusion
        (
            [],
            [],
            [
                "/usr",
                "/usr/bin",
                "/usr/share",
                "/usr/bin/hello",
                "/usr/share/doc",
                "/usr/share/doc/amhello",
                "/usr/share/doc/amhello/README",
                "/tests",
                "/tests/test",
            ],
        ),
        # Test only runtime
        (["runtime"], [], ["/usr", "/usr/share", "/usr/bin", "/usr/bin/hello"]),
        # Test with runtime and doc
        (
            ["runtime", "doc"],
            [],
            [
                "/usr",
                "/usr/share",
                "/usr/bin",
                "/usr/bin/hello",
                "/usr/share/doc",
                "/usr/share/doc/amhello",
                "/usr/share/doc/amhello/README",
            ],
        ),
        # Test with only runtime excluded
        (
            [],
            ["runtime"],
            [
                "/usr",
                "/usr/share",
                "/usr/share/doc",
                "/usr/share/doc/amhello",
                "/usr/share/doc/amhello/README",
                "/tests",
                "/tests/test",
            ],
        ),
        # Test with runtime and doc excluded
        ([], ["runtime", "doc"], ["/usr", "/usr/share", "/tests", "/tests/test"]),
        # Test with runtime simultaneously in- and excluded
        (["runtime"], ["runtime"], ["/usr", "/usr/share"]),
        # Test with runtime included and doc excluded
        (["runtime"], ["doc"], ["/usr", "/usr/share", "/usr/bin", "/usr/bin/hello"]),
        # Test including a custom 'test' domain
        (["test"], [], ["/usr", "/usr/share", "/tests", "/tests/test"]),
        # Test excluding a custom 'test' domain
        (
            [],
            ["test"],
            [
                "/usr",
                "/usr/bin",
                "/usr/share",
                "/usr/bin/hello",
                "/usr/share/doc",
                "/usr/share/doc/amhello",
                "/usr/share/doc/amhello/README",
            ],
        ),
    ],
)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_compose_include(cli, datafiles, include_domains, exclude_domains, expected):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "compose/compose-amhello.bst"

    # Create a yaml configuration from the specified include and
    # exclude domains
    config = {"include": include_domains, "exclude": exclude_domains}
    create_compose_element(element_name, element_path, config=config)

    result = cli.run(project=project, args=["source", "track", "compose/amhello.bst"])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

    assert set(walk_dir(checkout)) == set(expected)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="Root directory not writable with userchroot",
)
def test_compose_run_integration(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    element_path = os.path.join(project, "elements")
    element_name = "compose/compose-amhello.bst"

    element = {
        "kind": "compose",
        "depends": [
            {"filename": "compose/amhello.bst", "type": "build"},
            {"filename": "compose/test-integration.bst", "type": "build"},
        ],
        "config": {"include": ["runtime"]},
    }

    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    result = cli.run(project=project, args=["source", "track", "compose/amhello.bst"])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["build", element_name])
    assert result.exit_code == 0

    result = cli.run(project=project, args=["artifact", "checkout", element_name, "--directory", checkout])
    assert result.exit_code == 0

    test_file = os.path.join(checkout, "tests", "test")
    assert os.path.isfile(test_file)
