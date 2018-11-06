from buildstream import _yaml
from ..testutils import mock_os
from ..testutils.runcli import cli

import os
import pytest


KiB = 1024
MiB = (KiB * 1024)
GiB = (MiB * 1024)
TiB = (GiB * 1024)


def test_parse_size_over_1024T(cli, tmpdir):
    BLOCK_SIZE = 4096
    cli.configure({
        'cache': {
            'quota': 2048 * TiB
        }
    })
    project = tmpdir.join("main")
    os.makedirs(str(project))
    _yaml.dump({'name': 'main'}, str(project.join("project.conf")))

    bavail = (1025 * TiB) / BLOCK_SIZE
    patched_statvfs = mock_os.mock_statvfs(f_bavail=bavail, f_bsize=BLOCK_SIZE)
    with mock_os.monkey_patch("statvfs", patched_statvfs):
        result = cli.run(project, args=["build", "file.bst"])
        assert "1025T of available system storage" in result.stderr
