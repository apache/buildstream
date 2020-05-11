# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import uuid

import pytest

from buildstream import _yaml
from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX, BUILDBOX_RUN
from buildstream.exceptions import ErrorDomain
from buildstream import utils

from tests.testutils import create_artifact_share


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


# execute_shell()
#
# Helper to run `bst shell` and first ensure that the element is built
#
# Args:
#    cli (Cli): The cli runner fixture
#    project (str): The project directory
#    command (list): The command argv list
#    config (dict): A project.conf dictionary to composite over the default
#    mount (tuple): A (host, target) tuple for the `--mount` option
#    element (str): The element to build and run a shell with
#    isolate (bool): Whether to pass --isolate to `bst shell`
#
def execute_shell(cli, project, command, *, config=None, mount=None, element="base.bst", isolate=False):
    # Ensure the element is built
    result = cli.run_project_config(project=project, project_config=config, args=["build", element])
    assert result.exit_code == 0

    args = ["shell"]
    if isolate:
        args += ["--isolate"]
    if mount is not None:
        host_path, target_path = mount
        args += ["--mount", host_path, target_path]
    args += [element, "--", *command]

    return cli.run_project_config(project=project, project_config=config, args=args)


# Test running something through a shell, allowing it to find the
# executable
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_shell(cli, datafiles):
    project = str(datafiles)

    result = execute_shell(cli, project, ["echo", "Ponies!"])
    assert result.exit_code == 0
    assert result.output == "Ponies!\n"


# Test running an executable directly
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_executable(cli, datafiles):
    project = str(datafiles)

    result = execute_shell(cli, project, ["/bin/echo", "Horseys!"])
    assert result.exit_code == 0
    assert result.output == "Horseys!\n"


# Test shell environment variable explicit assignments
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
# This test seems to fail or pass depending on if this file is run or the hole test suite
def test_env_assign(cli, datafiles, animal):
    project = str(datafiles)
    expected = animal + "\n"

    result = execute_shell(
        cli, project, ["/bin/sh", "-c", "echo ${ANIMAL}"], config={"shell": {"environment": {"ANIMAL": animal}}}
    )

    assert result.exit_code == 0
    assert result.output == expected


# Test shell environment variable explicit assignments with host env var expansion
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
# This test seems to fail or pass depending on if this file is run or the hole test suite
def test_env_assign_expand_host_environ(cli, datafiles, animal):
    project = str(datafiles)
    expected = "The animal is: {}\n".format(animal)

    os.environ["BEAST"] = animal

    result = execute_shell(
        cli,
        project,
        ["/bin/sh", "-c", "echo ${ANIMAL}"],
        config={"shell": {"environment": {"ANIMAL": "The animal is: ${BEAST}"}}},
    )

    assert result.exit_code == 0
    assert result.output == expected


# Test that shell environment variable explicit assignments are discarded
# when running an isolated shell
@pytest.mark.parametrize("animal", [("Horse"), ("Pony")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
# This test seems to faili or pass depending on if this file is run or the hole test suite
def test_env_assign_isolated(cli, datafiles, animal):
    project = str(datafiles)
    result = execute_shell(
        cli,
        project,
        ["/bin/sh", "-c", "echo ${ANIMAL}"],
        isolate=True,
        config={"shell": {"environment": {"ANIMAL": animal}}},
    )

    assert result.exit_code == 0
    assert result.output == "\n"


# Test running an executable in a runtime with no shell (i.e., no
# /bin/sh)
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN == "buildbox-run-userchroot",
    reason="buildbox-run-userchroot requires a shell",
)
def test_no_shell(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, "elements")
    element_name = "shell/no-shell.bst"

    # Create an element that removes /bin/sh from the base runtime
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build"}],
        "variables": {"install-root": "/"},
        "config": {"commands": ["rm /bin/sh"]},
    }
    os.makedirs(os.path.dirname(os.path.join(element_path, element_name)), exist_ok=True)
    _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

    result = execute_shell(cli, project, ["/bin/echo", "Pegasissies!"], element=element_name)
    assert result.exit_code == 0
    assert result.output == "Pegasissies!\n"


# Test that bind mounts defined in project.conf work
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt"), (None)])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN != "buildbox-run-bubblewrap",
    reason="Only available with bubblewrap",
)
def test_host_files(cli, datafiles, path):
    project = str(datafiles)
    ponyfile = os.path.join(project, "files", "shell-mount", "pony.txt")
    if path is None:
        result = execute_shell(cli, project, ["cat", ponyfile], config={"shell": {"host-files": [ponyfile]}})
    else:
        result = execute_shell(
            cli, project, ["cat", path], config={"shell": {"host-files": [{"host_path": ponyfile, "path": path}]}}
        )
    assert result.exit_code == 0
    assert result.output == "pony\n"


# Test that bind mounts defined in project.conf work
@pytest.mark.parametrize("path", [("/etc"), ("/usr/share/pony")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN != "buildbox-run-bubblewrap",
    reason="Only available with bubblewrap",
)
def test_host_files_expand_environ(cli, datafiles, path):
    project = str(datafiles)
    hostpath = os.path.join(project, "files", "shell-mount")
    fullpath = os.path.join(path, "pony.txt")

    os.environ["BASE_PONY"] = path
    os.environ["HOST_PONY_PATH"] = hostpath

    result = execute_shell(
        cli,
        project,
        ["cat", fullpath],
        config={
            "shell": {"host-files": [{"host_path": "${HOST_PONY_PATH}/pony.txt", "path": "${BASE_PONY}/pony.txt"}]}
        },
    )
    assert result.exit_code == 0
    assert result.output == "pony\n"


# Test that bind mounts defined in project.conf dont mount in isolation
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_isolated_no_mount(cli, datafiles, path):
    project = str(datafiles)
    ponyfile = os.path.join(project, "files", "shell-mount", "pony.txt")
    result = execute_shell(
        cli,
        project,
        ["cat", path],
        isolate=True,
        config={"shell": {"host-files": [{"host_path": ponyfile, "path": path}]}},
    )
    assert result.exit_code != 0
    assert path in result.stderr
    assert "No such file or directory" in result.stderr


# Test that we warn about non-existing files on the host if the mount is not
# declared as optional, and that there is no warning if it is optional
@pytest.mark.parametrize("optional", [("mandatory"), ("optional")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_host_files_missing(cli, datafiles, optional):
    project = str(datafiles)
    ponyfile = os.path.join(project, "files", "shell-mount", "horsy.txt")

    option = optional == "optional"

    # Assert that we did successfully run something in the shell anyway
    result = execute_shell(
        cli,
        project,
        ["echo", "Hello"],
        config={"shell": {"host-files": [{"host_path": ponyfile, "path": "/etc/pony.conf", "optional": option}]}},
    )
    assert result.exit_code == 0
    assert result.output == "Hello\n"

    if option:
        # Assert that there was no warning about the mount
        assert ponyfile not in result.stderr
    else:
        # Assert that there was a warning about the mount
        assert ponyfile in result.stderr


# Test that bind mounts defined in project.conf work
@pytest.mark.parametrize("path", [("/etc/pony.conf"), ("/usr/share/pony/pony.txt")])
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.xfail(
    HAVE_SANDBOX == "buildbox-run" and BUILDBOX_RUN != "buildbox-run-bubblewrap",
    reason="Only available with bubblewrap",
)
def test_cli_mount(cli, datafiles, path):
    project = str(datafiles)
    ponyfile = os.path.join(project, "files", "shell-mount", "pony.txt")

    result = execute_shell(cli, project, ["cat", path], mount=(ponyfile, path))
    assert result.exit_code == 0
    assert result.output == "pony\n"


# Test that we can see the workspace files in a shell
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_workspace_visible(cli, datafiles):
    project = str(datafiles)
    workspace = os.path.join(cli.directory, "workspace")
    element_name = "workspace/workspace-mount-fail.bst"

    # Open a workspace on our build failing element
    #
    res = cli.run(project=project, args=["workspace", "open", "--directory", workspace, element_name])
    assert res.exit_code == 0

    # Ensure the dependencies of our build failing element are built
    result = cli.run(project=project, args=["build", "base.bst"])
    assert result.exit_code == 0

    # Obtain a copy of the hello.c content from the workspace
    #
    workspace_hello_path = os.path.join(cli.directory, "workspace", "hello.c")
    assert os.path.exists(workspace_hello_path)
    with open(workspace_hello_path, "r") as f:
        workspace_hello = f.read()

    # Cat the hello.c file from a bst shell command, and assert
    # that we got the same content here
    #
    result = cli.run(project=project, args=["shell", "--build", element_name, "--", "cat", "hello.c"])
    assert result.exit_code == 0
    assert result.output == workspace_hello


# Test system integration commands can access devices in /dev
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_integration_devices(cli, datafiles):
    project = str(datafiles)
    element_name = "integration.bst"

    result = execute_shell(cli, project, ["true"], element=element_name)
    assert result.exit_code == 0


# Test that a shell can be opened from an external workspace
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("build_shell", [("build"), ("nobuild")])
@pytest.mark.parametrize("guess_element", [True, False], ids=["guess", "no-guess"])
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_integration_external_workspace(cli, tmpdir_factory, datafiles, build_shell, guess_element):
    tmpdir = tmpdir_factory.mktemp(os.path.basename(__file__))
    project = str(datafiles)
    element_name = "autotools/amhello.bst"
    workspace_dir = os.path.join(str(tmpdir), "workspace")

    if guess_element:
        # Mutate the project.conf to use a default shell command
        project_file = os.path.join(project, "project.conf")
        config_text = "shell:\n  command: ['true']\n"
        with open(project_file, "a") as f:
            f.write(config_text)

    result = cli.run(project=project, args=["workspace", "open", "--directory", workspace_dir, element_name])
    result.assert_success()

    result = cli.run(project=project, args=["-C", workspace_dir, "build", element_name])
    result.assert_success()

    command = ["-C", workspace_dir, "shell"]
    if build_shell == "build":
        command.append("--build")
    if not guess_element:
        command.extend([element_name, "--", "true"])
    result = cli.run(project=project, cwd=workspace_dir, args=command)
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_integration_partial_artifact(cli, datafiles, tmpdir, integration_cache):

    project = str(datafiles)
    element_name = "autotools/amhello.bst"

    # push to an artifact server so we can pull from it later.
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure({"artifacts": {"url": share.repo, "push": True}})
        result = cli.run(project=project, args=["build", element_name])
        result.assert_success()

        # If the build is cached then it might not push to the artifact cache
        result = cli.run(project=project, args=["artifact", "push", element_name])
        result.assert_success()

        result = cli.run(project=project, args=["shell", element_name])
        result.assert_success()

        # do a checkout and get the digest of the hello binary.
        result = cli.run(
            project=project,
            args=[
                "artifact",
                "checkout",
                "--deps",
                "none",
                "--directory",
                os.path.join(str(tmpdir), "tmp"),
                "autotools/amhello.bst",
            ],
        )
        result.assert_success()
        digest = utils.sha256sum(os.path.join(str(tmpdir), "tmp", "usr", "bin", "hello"))

        # Remove the binary from the CAS
        cachedir = cli.config["cachedir"]
        objpath = os.path.join(cachedir, "cas", "objects", digest[:2], digest[2:])
        os.unlink(objpath)

        # check shell doesn't work
        result = cli.run(project=project, args=["shell", element_name, "--", "hello"])
        result.assert_main_error(ErrorDomain.APP, None)

        # check the artifact gets completed with '--pull' specified
        result = cli.run(project=project, args=["shell", "--pull", element_name, "--", "hello"])
        result.assert_success()
        assert "autotools/amhello.bst" in result.get_pulled_elements()


# Test that the sources are fetched automatically when opening a build shell
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_build_shell_fetch(cli, datafiles):
    project = str(datafiles)
    element_name = "build-shell-fetch.bst"

    # Create a file with unique contents such that it cannot be in the cache already
    test_filepath = os.path.join(project, "files", "hello.txt")
    test_message = "Hello World! {}".format(uuid.uuid4())
    with open(test_filepath, "w") as f:
        f.write(test_message)
    checksum = utils.sha256sum(test_filepath)

    # Create an element that has this unique file as a source
    element = {
        "kind": "manual",
        "depends": ["base.bst"],
        "sources": [{"kind": "remote", "url": "project_dir:/files/hello.txt", "ref": checksum}],
    }
    _yaml.roundtrip_dump(element, os.path.join(project, "elements", element_name))

    # Ensure our dependencies are cached
    result = cli.run(project=project, args=["build", "base.bst"])
    result.assert_success()

    # Ensure our sources are not cached
    assert cli.get_element_state(project, element_name) == "fetch needed"

    # Launching a shell should fetch any uncached sources
    result = cli.run(project=project, args=["shell", "--build", element_name, "cat", "hello.txt"])
    result.assert_success()
    assert result.output == test_message
