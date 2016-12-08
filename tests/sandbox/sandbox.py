import os
import pytest

from programs import (
    file_is_writable_test_program, file_or_directory_exists_test_program,
    session_tmpdir)

from buildstream._sandboxbwrap import SandboxBwrap, STDOUT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)


def test_no_output():
    """Test ignoring of stderr/stdout."""

    sandbox = SandboxBwrap(stdout=None, stderr=None)
    exit, out, err = sandbox.run(['echo', 'xyzzy'])

    assert exit == 0
    assert out is None
    assert err is None


def test_output():
    sandbox = SandboxBwrap()
    exit, out, err = sandbox.run(['echo', 'xyzzy'])

    assert exit == 0
    assert out.decode('unicode-escape') == 'xyzzy\n'
    assert err.decode('unicode-escape') == ''

    exit, out, err = sandbox.run(['sh', '-c', 'echo xyzzy >&2; exit 11'])

    assert exit == 11
    assert out.decode('unicode-escape') == ''
    assert err.decode('unicode-escape') == 'xyzzy\n'


@pytest.mark.tmpdir(os.path.join(DATA_DIR, 'output_redirection'))
def test_output_redirection(tmpdir):
    outlog_fp = str(tmpdir.join('outlog.txt'))
    errlog_fp = str(tmpdir.join('errlog.txt'))
    with open(outlog_fp, 'w') as outlog, open(errlog_fp, 'w') as errlog:
        sandbox = SandboxBwrap(stdout=outlog, stderr=errlog)
        exit, _, _ = sandbox.run(['sh', '-c', 'echo abcde; echo xyzzy >&2'])

    with open(outlog_fp) as outlog, open(errlog_fp) as errlog:
        assert outlog.read() == 'abcde\n'
        assert errlog.read() == 'xyzzy\n'

    with open(outlog_fp, 'w') as outlog, open(errlog_fp, 'w') as errlog:
        sandbox = SandboxBwrap(stdout=outlog, stderr=STDOUT)
        exit = sandbox.run(['sh', '-c', 'echo abcde; echo xyzzy >&2'])

    with open(outlog_fp) as outlog:
        assert outlog.read() == 'abcde\nxyzzy\n'


def test_current_working_directory(tmpdir):
    sandbox = SandboxBwrap(cwd=str(tmpdir))
    exit, out, err = sandbox.run(['pwd'])

    assert exit == 0
    assert out.decode('unicode-escape') == '%s\n' % str(tmpdir)
    assert err.decode('unicode-escape') == ''


def test_environment():
    sandbox = SandboxBwrap(env={'foo': 'bar'})
    exit, out, err = sandbox.run(['env'])

    assert exit == 0
    assert out.decode('unicode-escape') == 'foo=bar\nPWD=%s\n' % (os.getcwd(),)
    assert err.decode('unicode-escape') == ''


def test_isolated_network():
    # Network should be disabled by default
    sandbox = SandboxBwrap()
    exit, out, err = sandbox.run(
        ['sh', '-c', 'cat /proc/net/dev | sed 1,2d | cut -f1 -d:'])

    assert exit == 0
    assert out.decode('unicode-escape').strip() == 'lo'
    assert err.decode('unicode-escape') == ''

# TODO test_network()

# TODO test_uid() test_gid()


class TestMounts(object):
    @pytest.fixture()
    def mounts_test_sandbox(self, tmpdir,
                            file_or_directory_exists_test_program):
        sandbox_path = tmpdir.mkdir('sandbox')

        bin_path = sandbox_path.mkdir('bin')

        file_or_directory_exists_test_program.copy(bin_path)
        bin_path.join('test-file-or-directory-exists').chmod(0o755)

        return sandbox_path

    def test_mount_proc(self, mounts_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(mounts_test_sandbox))
        sandbox.set_mounts([{'dest': '/proc', 'type': 'proc'}])

        exit, out, err = sandbox.run(
            ['/bin/test-file-or-directory-exists', '/proc'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == "/proc exists"
        assert exit == 0

    def test_mount_tmpfs(self, mounts_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(mounts_test_sandbox))
        sandbox.set_mounts([{'dest': '/dev/shm', 'type': 'tmpfs'}])

        exit, out, err = sandbox.run(
            ['/bin/test-file-or-directory-exists', '/dev/shm'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == "/dev/shm exists"
        assert exit == 0


class TestWriteablePaths(object):
    @pytest.fixture()
    def writable_paths_test_sandbox(self, tmpdir,
                                    file_is_writable_test_program):
        sandbox_path = tmpdir.mkdir('sandbox')

        bin_path = sandbox_path.mkdir('bin')

        file_is_writable_test_program.copy(bin_path)
        bin_path.join('test-file-is-writable').chmod(0o755)

        data_path = sandbox_path.mkdir('data')
        data_path = data_path.mkdir('1')
        data_path.join('canary').write("Please don't overwrite me.")

        return sandbox_path

    def test_none_writable(self, writable_paths_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(writable_paths_test_sandbox))
        sandbox.debug = True

        exit, out, err = sandbox.run(
            ['/bin/test-file-is-writable', '/data/1/canary'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == \
            "Couldn't open /data/1/canary for writing."
        assert exit == 1

    def test_some_writable(self, writable_paths_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(writable_paths_test_sandbox))
        sandbox.set_mounts([{'src': 'data', 'dest': '/data', 'writable': True}])

        exit, out, err = sandbox.run(
            ['/bin/test-file-is-writable', '/data/1/canary'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == \
            "Wrote data to /data/1/canary."
        assert exit == 0

    def test_all_writable(self, writable_paths_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(writable_paths_test_sandbox))
        sandbox.set_mounts([{'src': 'data', 'dest': '/data'}], global_write=True)

        exit, out, err = sandbox.run(
            ['/bin/test-file-is-writable', '/data/1/canary'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == \
            "Wrote data to /data/1/canary."
        assert exit == 0

    def test_all_writable_ignore_override(self, writable_paths_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(writable_paths_test_sandbox))
        sandbox.set_mounts([{'src': 'data', 'dest': '/data', 'writable': False}], global_write=True)

        exit, out, err = sandbox.run(
            ['/bin/test-file-is-writable', '/data/1/canary'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == \
            "Wrote data to /data/1/canary."
        assert exit == 0

    def test_mount_point_not_writable(self, writable_paths_test_sandbox):
        sandbox = SandboxBwrap(fs_root=str(writable_paths_test_sandbox))
        sandbox.set_mounts([{'src': 'data', 'dest': '/data', 'writable': False}])

        exit, out, err = sandbox.run(
            ['/bin/test-file-is-writable', '/data/1/canary'])

        assert err.decode('unicode-escape') == ''
        assert out.decode('unicode-escape') == \
            "Couldn't open /data/1/canary for writing."
        assert exit == 1
