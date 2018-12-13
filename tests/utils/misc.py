import os
from unittest import mock

from buildstream import _yaml

from ..testutils.runcli import cli


KiB = 1024
MiB = (KiB * 1024)
GiB = (MiB * 1024)
TiB = (GiB * 1024)


def test_parse_size_over_1024T(cli, tmpdir):
    cli.configure({
        'cache': {
            'quota': 2048 * TiB
        }
    })
    project = tmpdir.join("main")
    os.makedirs(str(project))
    _yaml.dump({'name': 'main'}, str(project.join("project.conf")))

    volume_space_patch = mock.patch(
        "buildstream._artifactcache.artifactcache.ArtifactCache._get_volume_space_info_for",
        autospec=True,
        return_value=(1025 * TiB, 1025 * TiB)
    )

    with volume_space_patch:
        result = cli.run(project, args=["build", "file.bst"])
        failure_msg = 'Your system does not have enough available space to support the cache quota specified.'
        assert failure_msg in result.stderr
