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
from buildstream._testing import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "completions")

MAIN_COMMANDS = ["artifact ", "build ", "help ", "init ", "shell ", "show ", "source ", "workspace "]

MAIN_OPTIONS = [
    "--builders ",
    "-c ",
    "-C ",
    "--cache-buildtrees ",
    "--colors ",
    "--config ",
    "--debug ",
    "--default-mirror ",
    "--directory ",
    "--error-lines ",
    "--fetchers ",
    "--log-file ",
    "--max-jobs ",
    "--message-lines ",
    "--network-retries ",
    "--no-colors ",
    "--no-debug ",
    "--no-interactive ",
    "--no-strict ",
    "--no-verbose ",
    "-o ",
    "--option ",
    "--on-error ",
    "--pull-buildtrees ",
    "--pushers ",
    "--strict ",
    "--verbose ",
    "--version ",
]

SOURCE_COMMANDS = [
    "checkout ",
    "fetch ",
    "push ",
    "track ",
]

ARTIFACT_COMMANDS = [
    "checkout ",
    "delete ",
    "push ",
    "pull ",
    "log ",
    "list-contents ",
    "show ",
]

WORKSPACE_COMMANDS = ["close ", "list ", "open ", "reset "]

PROJECT_ELEMENTS = [
    "compose-all.bst",
    "compose-exclude-dev.bst",
    "compose-include-bin.bst",
    "import-bin.bst",
    "import-dev.bst",
    "target.bst",
]

INVALID_ELEMENTS = [
    "target.foo",
    "target.bst.bar",
]

MIXED_ELEMENTS = PROJECT_ELEMENTS + INVALID_ELEMENTS


def assert_completion(cli, cmd, word_idx, expected, cwd=None):
    result = cli.run(
        project=".", cwd=cwd, env={"_BST_COMPLETION": "complete", "COMP_WORDS": cmd, "COMP_CWORD": str(word_idx)}
    )
    words = []
    if result.output:
        words = result.output.splitlines()

    # The order is meaningless, bash will
    # take the results and order it by its
    # own little heuristics
    words = sorted(words)
    expected = sorted(expected)
    assert words == expected


def assert_completion_failed(cli, cmd, word_idx, expected, cwd=None):
    result = cli.run(cwd=cwd, env={"_BST_COMPLETION": "complete", "COMP_WORDS": cmd, "COMP_CWORD": str(word_idx)})
    words = []
    if result.output:
        words = result.output.splitlines()

    # The order is meaningless, bash will
    # take the results and order it by its
    # own little heuristics
    words = sorted(words)
    expected = sorted(expected)
    assert words != expected


@pytest.mark.parametrize(
    "cmd,word_idx,expected",
    [
        ("bst", 0, []),
        ("bst ", 1, MAIN_COMMANDS),
        ("bst artifact ", 2, ARTIFACT_COMMANDS),
        ("bst source ", 2, SOURCE_COMMANDS),
        ("bst w ", 1, ["workspace "]),
        ("bst workspace ", 2, WORKSPACE_COMMANDS),
    ],
)
def test_commands(cli, cmd, word_idx, expected):
    assert_completion(cli, cmd, word_idx, expected)


@pytest.mark.parametrize(
    "cmd,word_idx,expected",
    [
        ("bst -", 1, MAIN_OPTIONS),
        ("bst --l", 1, ["--log-file "]),
        # Test that options of subcommands also complete
        (
            "bst --no-colors build -",
            3,
            [
                "--deps ",
                "-d ",
                "--artifact-remote ",
                "--source-remote ",
                "--ignore-project-artifact-remotes ",
                "--ignore-project-source-remotes ",
            ],
        ),
        # Test the behavior of completing after an option that has a
        # parameter that cannot be completed, vs an option that has
        # no parameter
        ("bst --fetchers ", 2, []),
        ("bst --no-colors ", 2, MAIN_COMMANDS),
    ],
)
def test_options(cli, cmd, word_idx, expected):
    assert_completion(cli, cmd, word_idx, expected)


@pytest.mark.parametrize(
    "cmd,word_idx,expected",
    [
        ("bst --on-error ", 2, ["continue ", "quit ", "terminate "]),
        ("bst --cache-buildtrees ", 2, ["always ", "auto ", "never "]),
        ("bst show --deps ", 3, ["all ", "build ", "none ", "run "]),
        ("bst show --deps=", 2, ["all ", "build ", "none ", "run "]),
        ("bst show --deps b", 3, ["build "]),
        ("bst show --deps=b", 2, ["build "]),
        ("bst show --deps r", 3, ["run "]),
        ("bst source track --deps ", 4, ["all ", "build ", "none ", "run "]),
    ],
)
def test_option_choice(cli, cmd, word_idx, expected):
    assert_completion(cli, cmd, word_idx, expected)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize(
    "cmd,word_idx,expected,subdir",
    [
        # Note that elements/ and files/ are partial completions and
        # as such do not come with trailing whitespace
        ("bst --config ", 2, ["cache/", "elements/", "files/", "project.conf "], None),
        ("bst --log-file ", 2, ["cache/", "elements/", "files/", "project.conf "], None),
        ("bst --config f", 2, ["files/"], None),
        ("bst --log-file f", 2, ["files/"], None),
        ("bst --config files", 2, ["files/bin-files/", "files/dev-files/"], None),
        ("bst --log-file files", 2, ["files/bin-files/", "files/dev-files/"], None),
        ("bst --config files/", 2, ["files/bin-files/", "files/dev-files/"], None),
        ("bst --log-file elements/", 2, [os.path.join("elements", e) + " " for e in PROJECT_ELEMENTS], None),
        ("bst --config ../", 2, ["../cache/", "../elements/", "../files/", "../project.conf "], "files"),
        ("bst --config ../elements/", 2, [os.path.join("..", "elements", e) + " " for e in PROJECT_ELEMENTS], "files"),
        ("bst --config ../nofile", 2, [], "files"),
        ("bst --config /pony/rainbow/nobodyhas/this/file", 2, [], "files"),
    ],
)
def test_option_file(datafiles, cli, cmd, word_idx, expected, subdir):
    cwd = str(datafiles)
    if subdir:
        cwd = os.path.join(cwd, subdir)
    assert_completion(cli, cmd, word_idx, expected, cwd=cwd)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
@pytest.mark.parametrize(
    "cmd,word_idx,expected,subdir",
    [
        # Note that regular files like project.conf are not returned when
        # completing for a directory
        ("bst --directory ", 2, ["cache/", "elements/", "files/"], None),
        ("bst --directory elements/", 2, [], None),
        ("bst --directory ", 2, ["dev-files/", "bin-files/"], "files"),
        ("bst --directory ../", 2, ["../cache/", "../elements/", "../files/"], "files"),
    ],
)
def test_option_directory(datafiles, cli, cmd, word_idx, expected, subdir):
    cwd = str(datafiles)
    if subdir:
        cwd = os.path.join(cwd, subdir)
    assert_completion(cli, cmd, word_idx, expected, cwd=cwd)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project,cmd,word_idx,expected,subdir",
    [
        # When running in the project directory
        ("project", "bst show ", 2, [e + " " for e in PROJECT_ELEMENTS], None),
        (
            "project",
            "bst build com",
            2,
            ["compose-all.bst ", "compose-include-bin.bst ", "compose-exclude-dev.bst "],
            None,
        ),
        # When running from the files subdir
        ("project", "bst show ", 2, [e + " " for e in PROJECT_ELEMENTS], "files"),
        (
            "project",
            "bst build com",
            2,
            ["compose-all.bst ", "compose-include-bin.bst ", "compose-exclude-dev.bst "],
            "files",
        ),
        # When passing the project directory
        ("project", "bst --directory ../ show ", 4, [e + " " for e in PROJECT_ELEMENTS], "files"),
        (
            "project",
            "bst --directory ../ build com",
            4,
            ["compose-all.bst ", "compose-include-bin.bst ", "compose-exclude-dev.bst "],
            "files",
        ),
        # Also try multi arguments together
        ("project", "bst --directory ../ artifact checkout t ", 5, ["target.bst "], "files"),
        ("project", "bst --directory ../ artifact checkout --directory ", 6, ["bin-files/", "dev-files/"], "files"),
        # When running in the project directory
        ("no-element-path", "bst show ", 2, [e + " " for e in PROJECT_ELEMENTS] + ["files/"], None),
        (
            "no-element-path",
            "bst build com",
            2,
            ["compose-all.bst ", "compose-include-bin.bst ", "compose-exclude-dev.bst "],
            None,
        ),
        # When running from the files subdir
        ("no-element-path", "bst show ", 2, [e + " " for e in PROJECT_ELEMENTS] + ["files/"], "files"),
        (
            "no-element-path",
            "bst build com",
            2,
            ["compose-all.bst ", "compose-include-bin.bst ", "compose-exclude-dev.bst "],
            "files",
        ),
        # When passing the project directory
        ("no-element-path", "bst --directory ../ show ", 4, [e + " " for e in PROJECT_ELEMENTS] + ["files/"], "files"),
        ("no-element-path", "bst --directory ../ show f", 4, ["files/"], "files"),
        ("no-element-path", "bst --directory ../ show files/", 4, ["files/bin-files/", "files/dev-files/"], "files"),
        (
            "no-element-path",
            "bst --directory ../ build com",
            4,
            ["compose-all.bst ", "compose-include-bin.bst ", "compose-exclude-dev.bst "],
            "files",
        ),
        # Also try multi arguments together
        ("no-element-path", "bst --directory ../ artifact checkout t ", 5, ["target.bst "], "files"),
        (
            "no-element-path",
            "bst --directory ../ artifact checkout --directory ",
            6,
            ["bin-files/", "dev-files/"],
            "files",
        ),
        # When element-path have sub-folders
        ("sub-folders", "bst show base", 2, ["base/wanted.bst "], None),
        ("sub-folders", "bst show base/", 2, ["base/wanted.bst "], None),
    ],
)
def test_argument_element(datafiles, cli, project, cmd, word_idx, expected, subdir):
    cwd = os.path.join(str(datafiles), project)
    if subdir:
        cwd = os.path.join(cwd, subdir)
    assert_completion(cli, cmd, word_idx, expected, cwd=cwd)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "project,cmd,word_idx,expected,subdir",
    [
        # When element has invalid suffix
        ("project", "bst --directory ../ show ", 4, [e + " " for e in MIXED_ELEMENTS], "files")
    ],
)
def test_argument_element_invalid(datafiles, cli, project, cmd, word_idx, expected, subdir):
    cwd = os.path.join(str(datafiles), project)
    if subdir:
        cwd = os.path.join(cwd, subdir)
    assert_completion_failed(cli, cmd, word_idx, expected, cwd=cwd)


@pytest.mark.parametrize(
    "cmd,word_idx,expected",
    [
        ("bst he", 1, ["help "]),
        ("bst help ", 2, MAIN_COMMANDS),
        ("bst help artifact ", 3, ARTIFACT_COMMANDS),
        ("bst help in", 2, ["init "]),
        ("bst help source ", 3, SOURCE_COMMANDS),
        ("bst help artifact ", 3, ARTIFACT_COMMANDS),
        ("bst help w", 2, ["workspace "]),
        ("bst help workspace ", 3, WORKSPACE_COMMANDS),
    ],
)
def test_help_commands(cli, cmd, word_idx, expected):
    assert_completion(cli, cmd, word_idx, expected)


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_argument_artifact(cli, datafiles):
    project = str(datafiles)

    # Build an import element with no dependencies (this will generate one artifact with 2 keys)
    result = cli.run(project=project, args=["build", "import-bin.bst"])  # Has no dependencies
    result.assert_success()

    # Use hard coded artifact names, cache keys should be stable now
    artifacts = [
        "test/import-bin/b8eabff4ad70f954d6ba751340cff8f8e85cddd1537904cd107889b73f7b7041",
        "test/import-bin/c737117d716278363c8398879ab557446c6f35d3d7472b75cb2e956f622da704",
    ]

    # Test autocompletion of the artifact
    cmds = ["bst artifact log ", "bst artifact log t", "bst artifact log test/"]

    for i, cmd in enumerate(cmds):
        word_idx = 3
        result = cli.run(
            project=project,
            cwd=project,
            env={"_BST_COMPLETION": "complete", "COMP_WORDS": cmd, "COMP_CWORD": str(word_idx)},
        )

        if result.output:
            words = result.output.splitlines()  # This leaves an extra space on each e.g. ['foo.bst ']
            words = [word.strip() for word in words]

            # We should now be able to see the artifacts, but the order in which artifacts
            # are displayed in the completion list is not guaranteed to be ordered, so we
            # test for both orders.
            if i == 0:
                expected1 = PROJECT_ELEMENTS + artifacts
                expected2 = PROJECT_ELEMENTS + list(reversed(artifacts))
            elif i == 1:
                expected1 = ["target.bst"] + artifacts
                expected2 = ["target.bst"] + list(reversed(artifacts))
            elif i == 2:
                expected1 = artifacts
                expected2 = list(reversed(artifacts))

            assert words in (expected1, expected2)
