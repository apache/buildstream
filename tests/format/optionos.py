from contextlib import contextmanager
import os

import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream.plugintestutils.runcli import cli

DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@contextmanager
def override_uname_os(name):
    orig_uname = os.uname
    orig_tuple = tuple(os.uname())
    override_result = (name, orig_tuple[1],
                       orig_tuple[2], orig_tuple[3],
                       orig_tuple[4])

    def override():
        return override_result

    os.uname = override
    yield
    os.uname = orig_uname


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("uname,value,expected", [
    # Test explicitly provided arches
    ('Darwin', 'Linux', 'Linuxy'),
    ('SunOS', 'FreeBSD', 'FreeBSDy'),

    # Test automatically derived arches
    ('Linux', None, 'Linuxy'),
    ('Darwin', None, 'Darwiny'),

    # Test that explicitly provided arches dont error out
    # when the `uname` reported arch is not supported
    ('AIX', 'Linux', 'Linuxy'),
    ('HaikuOS', 'SunOS', 'SunOSy'),
])
def test_conditionals(cli, datafiles, uname, value, expected):
    with override_uname_os(uname):
        project = os.path.join(datafiles.dirname, datafiles.basename, 'option-os')

        bst_args = []
        if value is not None:
            bst_args += ['--option', 'machine_os', value]

        bst_args += [
            'show',
            '--deps', 'none',
            '--format', '%{vars}',
            'element.bst'
        ]
        result = cli.run(project=project, silent=True, args=bst_args)
        result.assert_success()

        loaded = _yaml.load_data(result.output)
        assert loaded['result'] == expected


@pytest.mark.datafiles(DATA_DIR)
def test_unsupported_arch(cli, datafiles):

    with override_uname_os("AIX"):
        project = os.path.join(datafiles.dirname, datafiles.basename, 'option-os')
        result = cli.run(project=project, silent=True, args=[
            'show',
            '--deps', 'none',
            '--format', '%{vars}',
            'element.bst'
        ])

        result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
