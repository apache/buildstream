import os
import pytest

from buildstream import _yaml
from buildstream.plugintestutils import cli_integration as cli
from tests.testutils.site import HAVE_SANDBOX


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


def create_script_element(name, path, config={}, variables={}):
    element = {
        'kind': 'script',
        'depends': [{
            'filename': 'base.bst',
            'type': 'build'
        }],
        'config': config,
        'variables': variables
    }
    os.makedirs(os.path.dirname(os.path.join(path, name)), exist_ok=True)
    _yaml.dump(element, os.path.join(path, name))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_script(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'script/script-layout.bst'

    create_script_element(element_name, element_path,
                          config={
                              'commands': [
                                  "mkdir -p %{install-root}",
                                  "echo 'Hi' > %{install-root}/test"
                              ],
                          })

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == "Hi\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_script_root(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'script/script-layout.bst'

    create_script_element(element_name, element_path,
                          config={
                              # Root-read only is False by default, we
                              # want to check the default here
                              # 'root-read-only': False,
                              'commands': [
                                  "mkdir -p %{install-root}",
                                  "echo 'I can write to root' > /test",
                                  "cp /test %{install-root}"
                              ],
                          })

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == "I can write to root\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_script_no_root(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_path = os.path.join(project, 'elements')
    element_name = 'script/script-layout.bst'

    create_script_element(element_name, element_path,
                          config={
                              'root-read-only': True,
                              'commands': [
                                  "mkdir -p %{install-root}",
                                  "echo 'I can not write to root' > /test",
                                  "cp /test %{install-root}"
                              ],
                          })

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code != 0

    assert "/test: Read-only file system" in res.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_script_cwd(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_path = os.path.join(project, 'elements')
    element_name = 'script/script-layout.bst'

    create_script_element(element_name, element_path,
                          config={
                              'commands': [
                                  "echo 'test' > test",
                                  "cp /buildstream/test %{install-root}"
                              ],
                          },
                          variables={
                              'cwd': '/buildstream'
                          })

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == "test\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_script_layout(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = 'script/script-layout.bst'

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    cli.run(project=project, args=['artifact', 'checkout', element_name, '--directory', checkout])
    assert res.exit_code == 0

    with open(os.path.join(checkout, 'test')) as f:
        text = f.read()

    assert text == "Hi\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_regression_cache_corruption(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout_original = os.path.join(cli.directory, 'checkout-original')
    checkout_after = os.path.join(cli.directory, 'checkout-after')
    element_name = 'script/corruption.bst'
    canary_element_name = 'script/corruption-image.bst'

    res = cli.run(project=project, args=['build', canary_element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', canary_element_name,
                                         '--directory', checkout_original])
    assert res.exit_code == 0

    with open(os.path.join(checkout_original, 'canary')) as f:
        assert f.read() == 'alive\n'

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', canary_element_name,
                                         '--directory', checkout_after])
    assert res.exit_code == 0

    with open(os.path.join(checkout_after, 'canary')) as f:
        assert f.read() == 'alive\n'


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_regression_tmpdir(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_name = 'script/tmpdir.bst'

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_regression_cache_corruption_2(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout_original = os.path.join(cli.directory, 'checkout-original')
    checkout_after = os.path.join(cli.directory, 'checkout-after')
    element_name = 'script/corruption-2.bst'
    canary_element_name = 'script/corruption-image.bst'

    res = cli.run(project=project, args=['build', canary_element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', canary_element_name,
                                         '--directory', checkout_original])
    assert res.exit_code == 0

    with open(os.path.join(checkout_original, 'canary')) as f:
        assert f.read() == 'alive\n'

    res = cli.run(project=project, args=['build', element_name])
    assert res.exit_code == 0

    res = cli.run(project=project, args=['artifact', 'checkout', canary_element_name,
                                         '--directory', checkout_after])
    assert res.exit_code == 0

    with open(os.path.join(checkout_after, 'canary')) as f:
        assert f.read() == 'alive\n'
