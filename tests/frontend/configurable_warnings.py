import pytest
import os

from buildstream.plugin import CoreWarnings
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream import _yaml
from tests.testutils.runcli import cli

TOP_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "configuredwarning"
)


def get_project(fatal_warnings):
    return {
        "name": "test",
        "element-path": "elements",
        "plugins": [
            {
                "origin": "local",
                "path": "plugins",
                "elements": {
                    "warninga": 0,
                    "warningb": 0,
                    "corewarn": 0,
                }
            }
        ],
        "fatal-warnings": fatal_warnings
    }


def build_project(datafiles, fatal_warnings):
    project_path = os.path.join(datafiles.dirname, datafiles.basename)

    project = get_project(fatal_warnings)

    _yaml.dump(project, os.path.join(project_path, "project.conf"))

    return project_path


@pytest.mark.datafiles(TOP_DIR)
@pytest.mark.parametrize("element_name, fatal_warnings, expect_fatal, error_domain", [
    ("corewarn.bst", [CoreWarnings.OVERLAPS], True, ErrorDomain.STREAM),
    ("warninga.bst", ["warninga:warning-a"], True, ErrorDomain.STREAM),
    ("warningb.bst", ["warningb:warning-b"], True, ErrorDomain.STREAM),
    ("corewarn.bst", [], False, None),
    ("warninga.bst", [], False, None),
    ("warningb.bst", [], False, None),
    ("warninga.bst", [CoreWarnings.OVERLAPS], False, None),
    ("warningb.bst", [CoreWarnings.OVERLAPS], False, None),
])
def test_fatal_warnings(cli, datafiles, element_name,
                        fatal_warnings, expect_fatal, error_domain):
    project_path = build_project(datafiles, fatal_warnings)

    result = cli.run(project=project_path, args=["build", element_name])
    if expect_fatal:
        result.assert_main_error(error_domain, None, "Expected fatal execution")
    else:
        result.assert_success("Unexpected fatal execution")
