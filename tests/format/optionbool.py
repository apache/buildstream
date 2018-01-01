import os
import pytest
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from tests.testutils.runcli import cli

# Project directory
DATA_DIR = os.path.dirname(os.path.realpath(__file__))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,option,expected", [
    # Test 'foo' syntax, and valid values of 'True' / 'False'
    ('element.bst', 'True', 'a pony'),
    ('element.bst', 'true', 'a pony'),
    ('element.bst', 'False', 'not pony'),
    ('element.bst', 'false', 'not pony'),

    # Test 'not foo' syntax
    ('element-not.bst', 'False', 'not pony'),
    ('element-not.bst', 'True', 'a pony'),

    # Test 'foo == True' syntax
    ('element-equals.bst', 'False', 'not pony'),
    ('element-equals.bst', 'True', 'a pony'),

    # Test 'foo != True' syntax
    ('element-not-equals.bst', 'False', 'not pony'),
    ('element-not-equals.bst', 'True', 'a pony'),
])
def test_conditional_cli(cli, datafiles, target, option, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-bool')
    result = cli.run(project=project, silent=True, args=[
        '--option', 'pony', option,
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        target])
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    assert loaded['thepony'] == expected


# Test configuration of boolean option in the config file
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("target,option,expected", [
    ('element.bst', True, 'a pony'),
    ('element.bst', False, 'not pony'),
])
def test_conditional_config(cli, datafiles, target, option, expected):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-bool')
    cli.configure({
        'projects': {
            'test': {
                'options': {
                    'pony': option
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
    assert loaded['thepony'] == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("cli_option", [
    ('falsey'), ('pony'), ('trUE')
])
def test_invalid_value_cli(cli, datafiles, cli_option):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-bool')
    result = cli.run(project=project, silent=True, args=[
        '--option', 'pony', cli_option,
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("config_option", [
    ('pony'), (['its', 'a', 'list']), ({'dic': 'tionary'})
])
def test_invalid_value_config(cli, datafiles, config_option):
    project = os.path.join(datafiles.dirname, datafiles.basename, 'option-bool')
    cli.configure({
        'projects': {
            'test': {
                'options': {
                    'pony': config_option
                }
            }
        }
    })
    result = cli.run(project=project, silent=True, args=[
        'show',
        '--deps', 'none',
        '--format', '%{vars}',
        'element.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)
