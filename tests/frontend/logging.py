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
import re

import pytest

from buildstream._testing import create_repo

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli  # pylint: disable=unused-import

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_default_logging(cli, tmpdir, datafiles):
    project = str(datafiles)
    bin_files_path = os.path.join(project, "files", "bin-files")
    element_path = os.path.join(project, "elements")
    element_name = "fetch-test-git.bst"

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # Now try to fetch it
    result = cli.run(project=project, args=["source", "fetch", element_name])
    result.assert_success()

    m = re.search(r"\[\d\d:\d\d:\d\d\]\[\s*\]\[.*\] SUCCESS Query cache", result.stderr)
    assert m is not None


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_custom_logging(cli, tmpdir, datafiles):
    project = str(datafiles)
    bin_files_path = os.path.join(project, "files", "bin-files")
    element_path = os.path.join(project, "elements")
    element_name = "fetch-test-git.bst"

    custom_log_format = "%{elapsed},%{elapsed-us},%{wallclock},%{wallclock-us},%{key},%{element},%{action},%{message}"
    user_config = {"logging": {"message-format": custom_log_format}}
    cli.configure(user_config)

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo("tar", str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    # Now try to fetch it
    result = cli.run(project=project, args=["source", "fetch", element_name])
    result.assert_success()

    m = re.search(
        r"\d\d:\d\d:\d\d,\d\d:\d\d:\d\d.\d{6},\d\d:\d\d:\d\d,\d\d:\d\d:\d\d.\d{6}\s*,.*" r",SUCCESS,Query cache",
        result.stderr,
    )
    assert m is not None


@pytest.mark.datafiles(os.path.join(DATA_DIR, "project"))
def test_failed_build_listing(cli, datafiles):
    project = str(datafiles)
    element_names = []
    for i in range(3):
        element_name = "testfail-{}.bst".format(i)
        element_path = os.path.join("elements", element_name)
        element = {"kind": "script", "config": {"commands": ["false"]}}
        _yaml.roundtrip_dump(element, os.path.join(project, element_path))
        element_names.append(element_name)
    result = cli.run(project=project, args=["--on-error=continue", "build", *element_names])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Check that we re-print the failure summaries only in the "Failure Summary"
    # section.
    # e.g.
    #
    # Failure Summary
    #   testfail-0.bst:
    #     [00:00:00][44f1b8c3][   build:testfail-0.bst                ] FAILURE Running 'commands'
    #
    failure_heading_pos = re.search(r"^Failure Summary$", result.stderr, re.MULTILINE).start()
    pipeline_heading_pos = re.search(r"^Pipeline Summary$", result.stderr, re.MULTILINE).start()
    failure_summary_range = range(failure_heading_pos, pipeline_heading_pos)
    matches = tuple(re.finditer(r"^\s+testfail-.\.bst:$", result.stderr, re.MULTILINE))
    for m in matches:
        assert m.start() in failure_summary_range
        assert m.end() in failure_summary_range
    assert len(matches) == 3  # each element should be matched once.

    # Note that if we mess up the 'element_name' of Messages, they won't be printed
    # with the name of the relevant element, e.g. 'testfail-1.bst'. Check that
    # they have the name as expected.
    pattern = r"\[..:..:..\] FAILURE \[.*\] testfail-.\.bst: Staged artifacts do not provide command 'sh'"
    assert len(re.findall(pattern, result.stderr, re.MULTILINE)) == 6  # each element should be matched twice.


# This test ensures that we get the expected element name and cache key in log lines.
#
#   * The master build log should show the element name and cache key
#     of the task element, i.e. the element currently being built, not
#     the element issuing the message.
#
#   * In the individual task log, we expect to see the name and cache
#     key of the element issuing messages, since the entire log file
#     is contextual to the task, it makes more sense to provide the
#     full context of the element issuing the log in this case.
#
# The order and format of log lines are UI and as such might change
# in which case this test needs to be adapted, the important part of
# this test is only that we see task elements reported in the aggregated
# master log file, and that we see message originating elements in
# a task specific log file.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR, "logging"))
def test_log_line_element_names(cli, datafiles):

    project = str(datafiles)

    # First discover the cache keys, this will give us a dictionary
    # where we can look up the brief cache key (as displayed in the logs)
    # by the element name.
    #
    keys = {}
    result = cli.run(project=project, args=["show", "--deps", "all", "--format", "%{name}||%{key}", "logtest.bst"])
    result.assert_success()
    lines = result.output.splitlines()
    for line in lines:
        split = line.split(sep="||")
        keys[split[0]] = split[1]

    # Run a build of the import elements, so that we can observe only the build of the logtest.bst element
    # at the end.
    #
    result = cli.run(project=project, args=["build", "foo.bst", "bar.bst"])

    # Now run the build
    #
    result = cli.run(project=project, args=["build", "logtest.bst"])
    result.assert_success()
    master_log = result.stderr

    # Now run `bst artifact log` to conveniently collect the build log so we can compare it.
    logfiles = os.path.join(project, "logfiles")
    logfile = os.path.join(project, "logfiles", "logtest.log")
    result = cli.run(project=project, args=["artifact", "log", "--out", logfiles, "logtest.bst"])
    result.assert_success()

    with open(logfile, "r", encoding="utf-8") as f:
        task_log = f.read()

    #########################################################
    #              Parse and assert master log              #
    #########################################################

    # In the master log, we're looking for lines like this:
    #
    # [--:--:--][10dc28c5][   build:logtest.bst                   ] STATUS  Staging bar.bst/40ff1c5a
    # [--:--:--][10dc28c5][   build:logtest.bst                   ] STATUS  Staging foo.bst/e5ab75a1

    # Capture (log key, element name, staged element name, staged element key)
    pattern = r"\[--:--:--\]\[(\S*)\]\[\s*build:(\S*)\s*] STATUS  Staging\s*(\S*)/(\S*)"
    lines = re.findall(pattern, master_log, re.MULTILINE)

    # We staged 2 elements
    assert len(lines) == 2

    # Assert that the logtest.bst element name and it's cache key is used in the master log
    for line in lines:
        log_key, log_name, staged_name, staged_key = line

        assert log_name == "logtest.bst"
        assert log_key == keys["logtest.bst"]

    #########################################################
    #              Parse and assert artifact log            #
    #########################################################

    # In the task specific build log, we're looking for lines like this:
    #
    # [--:--:--] STATUS  [40ff1c5a] bar.bst: Staging bar.bst/40ff1c5a
    # [--:--:--] STATUS  [e5ab75a1] foo.bst: Staging foo.bst/e5ab75a1

    # Capture (log key, element name, staged element name, staged element key)
    pattern = r"\[--:--:--\] STATUS  \[(\S*)\] (\S*): Staging\s*(\S*)/(\S*)"
    lines = re.findall(pattern, task_log, re.MULTILINE)

    # We staged 2 elements
    assert len(lines) == 2

    # Assert that the originating element names and cache keys are used in
    # log lines when recorded to the task specific log file
    for line in lines:
        log_key, log_name, staged_name, staged_key = line

        assert log_name == staged_name
        assert log_key == staged_key
        assert log_key == keys[log_name]
