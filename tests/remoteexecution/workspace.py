# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream.testing import cli_remote_execution as cli  # pylint: disable=unused-import
from buildstream.testing.integration import assert_contains

pytestmark = pytest.mark.remoteexecution


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")
MKFILEAM = os.path.join("src", "Makefile.am")
MKFILE = os.path.join("src", "Makefile")
MAIN = os.path.join("src", "main.o")
CFGMARK = "config-time"
BLDMARK = "build-time"


def files():
    _input_files = [
        ".bstproject.yaml",
        "aclocal.m4",
        "missing",
        "README",
        "install-sh",
        "depcomp",
        "configure.ac",
        "compile",
        "src",
        os.path.join("src", "main.c"),
        MKFILEAM,
        "Makefile.am",
    ]
    input_files = [os.sep + fname for fname in _input_files]

    _generated_files = [
        "Makefile",
        "Makefile.in",
        "autom4te.cache",
        os.path.join("autom4te.cache", "traces.1"),
        os.path.join("autom4te.cache", "traces.0"),
        os.path.join("autom4te.cache", "requests"),
        os.path.join("autom4te.cache", "output.0"),
        os.path.join("autom4te.cache", "output.1"),
        "config.h",
        "config.h.in",
        "config.log",
        "config.status",
        "configure",
        "configure.lineno",
        os.path.join("src", "hello"),
        os.path.join("src", ".deps"),
        os.path.join("src", ".deps", "main.Po"),
        MKFILE,
        MAIN,
        CFGMARK,
        BLDMARK,
        os.path.join("src", "Makefile.in"),
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
    for dirname, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        for subdirname in dirnames:
            fname = os.path.join(dirname, subdirname)
            yield fname[len(root) :], os.stat(fname).st_mtime
        for filename in filenames:
            fname = os.path.join(dirname, filename)
            yield fname[len(root) :], os.stat(fname).st_mtime


def get_mtimes(root):
    return dict(set(_get_mtimes(root)))


def check_buildtree(
    cli, project, element_name, input_files, generated_files, incremental=False,
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
            "always",
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
    inp_times = []
    gen_times = []
    output = result.output.splitlines()

    for line in output:
        assert "::" in line
        fname, mtime = line.split("::")
        # remove the symbolic dir
        fname = fname[1:]
        mtime = int(mtime)
        buildtree[fname] = mtime

        if incremental:
            if fname in input_files:
                inp_times.append(mtime)
            else:
                gen_times.append(mtime)

    # all expected files should have been found
    for filename in input_files + generated_files:
        assert filename in buildtree

    if incremental:
        # at least inputs should be older than generated files
        assert not any([inp_time > gen_time for inp_time in inp_times for gen_time in gen_times])

        makefile = os.sep + "Makefile"
        makefile_am = os.sep + "Makefile.am"
        mainc = os.sep + os.path.join("src", "main.c")
        maino = os.sep + os.path.join("src", "hello")
        testfiles = [makefile, makefile_am, mainc, maino]
        if all([testfile in buildtree for testfile in testfiles]):
            assert buildtree[makefile] < buildtree[makefile_am]
            assert buildtree[mainc] < buildtree[maino]

    return buildtree


def get_timemark(cli, project, element_name, marker):
    result = cli.run(
        project=project, args=["shell", "--build", element_name, "--use-buildtree", "always", "--", "cat", marker[1:]],
    )
    result.assert_success()
    marker_time = int(result.output)
    return marker_time


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "modification",
    [
        pytest.param("none"),
        pytest.param("content"),
        pytest.param("time", marks=pytest.mark.xfail(reason="mtimes are set to a magic value and not stored in CAS")),
    ],
)
@pytest.mark.parametrize(
    "buildtype",
    [
        pytest.param("non-incremental"),
        pytest.param(
            "incremental", marks=pytest.mark.xfail(reason="incremental workspace builds are not yet supported")
        ),
    ],
)
def test_workspace_build(cli, tmpdir, datafiles, modification, buildtype):
    incremental = False
    if buildtype == "incremental":
        incremental = True

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
    with open(newfile_path, "w") as fdata:
        fdata.write("somestring")
    input_files.append(os.sep + newfile)

    # check that the workspace *only* contains the expected input files
    assert_contains(workspace, input_files, strict=True)
    # save the mtimes for later comparison
    ws_times = get_mtimes(workspace)

    # build the element and cache the buildtree
    result = cli.run(project=project, args=build)
    result.assert_success()

    # check that the local workspace is unchanged
    assert_contains(workspace, input_files, strict=True)
    assert ws_times == get_mtimes(workspace)

    # check modified workspace dir was cached and save the time
    # build was run
    build_mtimes = check_buildtree(cli, project, element_name, input_files, generated_files, incremental=incremental)
    build_timemark = get_timemark(cli, project, element_name, (os.sep + BLDMARK))

    # check that the artifacts are available
    result = cli.run(project=project, args=artifact_checkout)
    result.assert_success()
    assert_contains(checkout, artifacts)
    shutil.rmtree(checkout)

    # rebuild the element
    result = cli.run(project=project, args=build)
    result.assert_success()
    # this should all be cached
    # so the buildmark time should be the same
    rebuild_mtimes = check_buildtree(cli, project, element_name, input_files, generated_files, incremental=incremental)
    rebuild_timemark = get_timemark(cli, project, element_name, (os.sep + BLDMARK))

    assert build_timemark == rebuild_timemark
    assert build_mtimes == rebuild_mtimes

    # modify the open workspace and rebuild
    if modification != "none":
        assert os.path.exists(newfile_path)

        if modification == "time":
            # touch a file in the workspace and save the mtime
            os.utime(newfile_path)

        elif modification == "content":
            # change a source file
            with open(newfile_path, "w") as fdata:
                fdata.write("anotherstring")

        # refresh input times
        ws_times = get_mtimes(workspace)

        # rebuild the element
        result = cli.run(project=project, args=build)
        result.assert_success()

        rebuild_mtimes = check_buildtree(
            cli, project, element_name, input_files, generated_files, incremental=incremental
        )
        rebuild_timemark = get_timemark(cli, project, element_name, (os.sep + BLDMARK))
        assert build_timemark != rebuild_timemark

        # check the times of the changed files
        if incremental:
            touched_time = os.stat(newfile_path).st_mtime
            assert rebuild_mtimes[newfile] == touched_time

        # Check workspace is unchanged
        assert_contains(workspace, input_files, strict=True)
        assert ws_times == get_mtimes(workspace)
