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
import shutil
import pytest

from buildstream._testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream._testing.integration import assert_contains
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON

pytestmark = pytest.mark.remoteexecution


# subdirectories of the buildtree
SRC = "src"
DEPS = os.path.join(SRC, ".deps")
AUTO = "autom4te.cache"
DIRS = [os.sep + SRC, os.sep + DEPS, os.sep + AUTO]

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")
MAIN = os.path.join(SRC, "main.c")
MAINO = os.path.join(SRC, "main.o")
CFGMARK = "config-time"
BLDMARK = "build-time"


def files():
    _input_files = [
        ".bstproject.yaml",
        "aclocal.m4",
        "README",
        "configure.ac",
        SRC,
        MAIN,
        os.path.join(SRC, "Makefile.am"),
        "Makefile.am",
    ]
    input_files = [os.sep + fname for fname in _input_files]

    _generated_files = [
        "Makefile",
        "Makefile.in",
        AUTO,
        os.path.join(AUTO, "traces.1"),
        os.path.join(AUTO, "traces.0"),
        os.path.join(AUTO, "requests"),
        os.path.join(AUTO, "output.0"),
        os.path.join(AUTO, "output.1"),
        "compile",
        "config.h",
        "config.h.in",
        "config.log",
        "config.status",
        "configure",
        "configure.lineno",
        "depcomp",
        "install-sh",
        "missing",
        os.path.join(SRC, "hello"),
        DEPS,
        os.path.join(DEPS, "main.Po"),
        os.path.join(SRC, "Makefile"),
        MAINO,
        CFGMARK,
        BLDMARK,
        os.path.join(SRC, "Makefile.in"),
        "stamp-h1",
    ]
    generated_files = [os.sep + fname for fname in _generated_files]

    _artifacts = [
        "usr",
        os.path.join("usr", "lib"),
        os.path.join("usr", "bin"),
        os.path.join("usr", "share"),
        os.path.join("usr", "bin", "hello"),
        os.path.join("usr", "share", "doc"),
        os.path.join("usr", "share", "doc", "amhello"),
        os.path.join("usr", "share", "doc", "amhello", "README"),
    ]
    artifacts = [os.sep + fname for fname in _artifacts]
    return input_files, generated_files, artifacts


def _get_mtimes(root):
    assert os.path.exists(root)
    # timestamps on subdirs are not currently semantically meaningful
    for dirname, _, filenames in os.walk(root):
        filenames.sort()
        for filename in filenames:
            fname = os.path.join(dirname, filename)
            yield fname[len(root) :], os.stat(fname).st_mtime


def get_mtimes(root):
    return dict(set(_get_mtimes(root)))


def check_buildtree(
    cli,
    project,
    element_name,
    input_files,
    generated_files,
    incremental=False,
):
    # check modified workspace dir was cached
    #   - generated files are present
    #   - generated files are newer than inputs
    #   - check the date recorded in the marker file
    #   - check that the touched file mtime is preserved from before

    assert cli and project and element_name and input_files and generated_files

    result = cli.run(
        project=project,
        args=[
            "shell",
            "--build",
            element_name,
            "--use-buildtree",
            "--",
            "find",
            ".",
            "-mindepth",
            "1",
            "-exec",
            "stat",
            "-c",
            "%n::%Y",
            "{}",
            ";",
        ],
    )
    result.assert_success()

    buildtree = {}
    output = result.output.splitlines()

    typ_inptime = None
    typ_gentime = None

    for line in output:
        assert "::" in line
        fname, mtime = line.split("::")
        # remove the symbolic dir
        fname = fname[1:]
        mtime = int(mtime)
        buildtree[fname] = mtime

        if incremental:
            # directory timestamps are not meaningful
            if fname in DIRS:
                continue
            if fname in input_files:
                if fname != os.sep + MAIN and not typ_inptime:
                    typ_inptime = mtime
            if fname in generated_files:
                if fname != os.sep + MAINO and not typ_gentime:
                    typ_gentime = mtime

    # all expected files should have been found
    for filename in input_files + generated_files:
        assert filename in buildtree

    if incremental:
        # the source file was changed so should be more recent than other input files
        # it should be older than the main object.
        # The main object should be more recent than generated files.
        assert buildtree[os.sep + MAIN] > typ_inptime
        assert buildtree[os.sep + MAINO] > buildtree[os.sep + MAIN]
        assert buildtree[os.sep + MAINO] > typ_gentime

    for fname in DIRS:
        del buildtree[fname]

    return buildtree


def get_timemark(cli, project, element_name, marker):
    result = cli.run(
        project=project,
        args=["shell", "--build", element_name, "--use-buildtree", "--", "cat", marker[1:]],
    )
    result.assert_success()
    marker_time = int(result.output)
    return marker_time


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "modification",
    [
        pytest.param("content"),
        pytest.param("time"),
    ],
)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_workspace_build(cli, tmpdir, datafiles, modification):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")
    workspace = os.path.join(cli.directory, "workspace")
    element_name = "autotools/amhello.bst"

    # cli args
    artifact_checkout = ["artifact", "checkout", element_name, "--directory", checkout]
    build = ["--cache-buildtrees", "always", "build", element_name]
    input_files, generated_files, artifacts = files()

    services = cli.ensure_services()
    assert set(services) == set(["action-cache", "execution", "storage"])

    # open a workspace for the element in the workspace directory
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace, element_name])
    result.assert_success()

    # check that the workspace path exists
    assert os.path.exists(workspace)

    # add a file (asserting later that this is in the buildtree)
    newfile = "newfile.cfg"
    newfile_path = os.path.join(workspace, newfile)
    with open(newfile_path, "w", encoding="utf-8") as fdata:
        fdata.write("somestring")
    input_files.append(os.sep + newfile)

    # check that the workspace *only* contains the expected input files
    assert_contains(workspace, input_files, strict=True)
    # save the mtimes for later comparison
    ws_times = get_mtimes(workspace)

    # build the element and cache the buildtree
    result = cli.run(project=project, args=build)
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    build_key = cli.get_element_key(project, element_name)

    # check that the local workspace is unchanged
    assert_contains(workspace, input_files, strict=True)
    assert ws_times == get_mtimes(workspace)

    # check modified workspace dir was cached and save the time
    # build was run. Incremental build conditions do not apply since the workspace
    # was initially opened using magic timestamps.
    build_times = check_buildtree(cli, project, element_name, input_files, generated_files, incremental=False)
    build_timemark = get_timemark(cli, project, element_name, (os.sep + BLDMARK))

    # check that the artifacts are available
    result = cli.run(project=project, args=artifact_checkout)
    result.assert_success()
    assert_contains(checkout, artifacts)
    shutil.rmtree(checkout)

    # rebuild the element
    result = cli.run(project=project, args=build)
    result.assert_success()
    assert cli.get_element_state(project, element_name) == "cached"
    rebuild_key = cli.get_element_key(project, element_name)
    assert rebuild_key == build_key
    rebuild_times = check_buildtree(cli, project, element_name, input_files, generated_files, incremental=False)
    rebuild_timemark = get_timemark(cli, project, element_name, (os.sep + BLDMARK))

    # buildmark time should be the same
    assert build_timemark == rebuild_timemark
    assert all(rebuild_time == build_times[fname] for fname, rebuild_time in rebuild_times.items()), "{}\n{}".format(
        rebuild_times, build_times
    )

    # modify the open workspace and rebuild
    main_path = os.path.join(workspace, MAIN)
    assert os.path.exists(main_path)

    if modification == "time":
        # touch a file in the workspace and save the mtime
        os.utime(main_path)
        touched_time = int(os.stat(main_path).st_mtime)

    elif modification == "content":
        # change a source file (there's a race here but it's not serious)
        with open(main_path, "r", encoding="utf-8") as fdata:
            data = fdata.readlines()
        with open(main_path, "w", encoding="utf-8") as fdata:
            for line in data:
                fdata.write(re.sub(r"Hello", "Goodbye", line))
        touched_time = int(os.stat(main_path).st_mtime)

    # refresh input times
    ws_times = get_mtimes(workspace)

    # rebuild the element
    result = cli.run(project=project, args=build)
    result.assert_success()

    rebuild_times = check_buildtree(cli, project, element_name, input_files, generated_files, incremental=True)
    rebuild_timemark = get_timemark(cli, project, element_name, (os.sep + BLDMARK))
    assert rebuild_timemark > build_timemark

    # check the times of the changed files
    assert rebuild_times[os.sep + MAIN] == touched_time
    del rebuild_times[os.sep + MAIN]
    del rebuild_times[os.sep + MAINO]
    del rebuild_times[os.sep + SRC + os.sep + "hello"]
    del rebuild_times[os.sep + DEPS + os.sep + "main.Po"]
    del rebuild_times[os.sep + BLDMARK]

    # check the times of the unmodified files
    assert all(rebuild_time == build_times[fname] for fname, rebuild_time in rebuild_times.items()), "{}\n{}".format(
        rebuild_times, build_times
    )

    # Check workspace is unchanged
    assert_contains(workspace, input_files, strict=True)
    assert ws_times == get_mtimes(workspace)
