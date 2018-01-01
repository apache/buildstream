import os
import pytest
from contextlib import contextmanager
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


# Context manager to override the reported value of `os.uname()`
@contextmanager
def override_uname_arch(name):
    orig_uname = os.uname
    orig_tuple = tuple(os.uname())
    override_result = (orig_tuple[0], orig_tuple[1],
                       orig_tuple[2], orig_tuple[3],
                       name)

    def override():
        return override_result

    os.uname = override
    yield
    os.uname = orig_uname


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("uname,value,expected", [
    # Test explicitly provided arches
    ('arm', 'arm', 'Army'),
    ('arm', 'aarch64', 'Aarchy'),

    # Test automatically derived arches
    ('arm', None, 'Army'),
    ('aarch64', None, 'Aarchy'),

    # Test that explicitly provided arches dont error out
    # when the `uname` reported arch is not supported
    ('i386', 'arm', 'Army'),
    ('x86_64', 'aarch64', 'Aarchy'),
])
def test_conditional(cli, datafiles, uname, value, expected):
    with override_uname_arch(uname):
        project = os.path.join(datafiles.dirname, datafiles.basename, 'option-arch')

        bst_args = []
        if value is not None:
            bst_args += ['--option', 'machine_arch', value]

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

    with override_uname_arch("x86_64"):
        project = os.path.join(datafiles.dirname, datafiles.basename, 'option-arch')
        result = cli.run(project=project, silent=True, args=[
            'show',
            '--deps', 'none',
            '--format', '%{vars}',
            'element.bst'
        ])

        result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
