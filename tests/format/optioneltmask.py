import os
import pytest
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,value,expected", [
    ('pony.bst', 'pony.bst', 'True'),
    ('horsy.bst', 'pony.bst, horsy.bst', 'True'),
    ('zebry.bst', 'pony.bst, horsy.bst', 'False'),
])
def test_conditional_cli(cli, datafiles, target, value, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-element-mask')
    result = cli.run(project=project, silent=True, args=[
        '--option', 'debug_elements', value,
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        target])

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['debug'] == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,value,expected", [
    ('pony.bst', ['pony.bst'], 'True'),
    ('horsy.bst', ['pony.bst', 'horsy.bst'], 'True'),
    ('zebry.bst', ['pony.bst', 'horsy.bst'], 'False'),
])
def test_conditional_config(cli, datafiles, target, value, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-element-mask')
    cli.configure({
        'projects': {
            'test': {
                'options': {
                    'debug_elements': value
                }
            }
        }
    })
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        target])

    result.assert_success()
    loaded = _yaml.load_data(result.output)
    assert loaded['debug'] == expected


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_declaration(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-element-mask-invalid')
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'pony.bst'])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_value(cli, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-element-mask')
    result = cli.run(project=project, silent=True, args=[
        '--option', 'debug_elements', 'kitten.bst',
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'pony.bst'])

    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
