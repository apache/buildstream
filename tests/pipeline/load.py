import os
import pytest
from buildstream._exceptions import ErrorDomain
from buildstream import _yaml
from tests.testutils.runcli import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(cli, datafiles):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.get_element_config(basedir, 'simple.bst')

    assert(result['configure-commands'][0] == 'pony')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'noloadref'))
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_unsupported_load_ref(cli, datafiles, ref_storage):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)

    # Generate project with access to the noloadref plugin and project.refs enabled
    #
    config = {
        'name': 'test',
        'ref-storage': ref_storage,
        'plugins': [
            {
                'origin': 'local',
                'path': 'plugins',
                'sources': {
                    'noloadref': 0
                }
            }
        ]
    }
    _yaml.dump(config, os.path.join(basedir, 'project.conf'))

    result = cli.run(project=basedir, silent=True, args=['show', 'noloadref.bst'])

    # There is no error if project.refs is not in use, otherwise we
    # assert our graceful failure
    if ref_storage == 'inline':
        result.assert_success()
    else:
        result.assert_main_error(ErrorDomain.SOURCE, 'unsupported-load-ref')
