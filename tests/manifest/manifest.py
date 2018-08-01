import pytest
import os
from ruamel import yaml

from tests.testutils import cli

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("specify_path, build_manifest", [
    (True, True), (True, False), (False, True)
])
def test_manifest_created(tmpdir, cli, datafiles, specify_path, build_manifest):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    manifest_path = os.path.join(str(tmpdir), "build_manifest.yaml")

    args = ['build', "base.bst"]

    if specify_path:
        args += ["--manifest-path", manifest_path]
    if build_manifest:
        args.append("--build-manifest")

    result = cli.run(project=project, args=args)
    result.assert_success()

    with open(manifest_path) as f:
        manifest = yaml.load(f, Loader=yaml.loader.RoundTripLoader)

    assert len(manifest["Elements"]["base"]["Sources"]) == 1


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("extension, valid", [
    (".yaml", True),
    (".yml", True),
    (".bst", False),
    (".ynl", False),
    (".xml", False),
    (".mnf", False),
    (".txt", False),
    (".abc", False),
    (".json", False)
])
def test_manifest_extensions(tmpdir, cli, datafiles, extension, valid):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    manifest_path = os.path.join(str(tmpdir), "build_manifest{}" + extension)

    result = cli.run(project=project, args=['build', "base.bst", "--manifest-path", manifest_path])

    if valid:
        result.assert_success()
    else:
        assert result.exit_code == 2
