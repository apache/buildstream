import os
import pytest

from buildstream._context import Context
from buildstream._exceptions import LoadError, LoadErrorReason

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)


# Simple fixture to create a Context object.
@pytest.fixture()
def context_fixture():
    if os.environ.get('XDG_CACHE_HOME'):
        cache_home = os.environ['XDG_CACHE_HOME']
    else:
        cache_home = os.path.expanduser('~/.cache')

    return {
        'xdg-cache': cache_home,
        'context': Context()
    }


#######################################
#        Test instantiation           #
#######################################
def test_context_create(context_fixture):
    context = context_fixture['context']
    assert(isinstance(context, Context))


#######################################
#     Test configuration loading      #
#######################################
def test_context_load(context_fixture):
    context = context_fixture['context']
    cache_home = context_fixture['xdg-cache']
    assert(isinstance(context, Context))

    context.load(config=os.devnull)
    assert(context.sourcedir == os.path.join(cache_home, 'buildstream', 'sources'))
    assert(context.builddir == os.path.join(cache_home, 'buildstream', 'build'))
    assert(context.artifactdir == os.path.join(cache_home, 'buildstream', 'artifacts'))
    assert(context.logdir == os.path.join(cache_home, 'buildstream', 'logs'))


# Assert that a changed XDG_CACHE_HOME doesn't cause issues
def test_context_load_envvar(context_fixture):
    os.environ['XDG_CACHE_HOME'] = '/some/path/'

    context = context_fixture['context']
    assert(isinstance(context, Context))

    context.load(config=os.devnull)
    assert(context.sourcedir == os.path.join('/', 'some', 'path', 'buildstream', 'sources'))
    assert(context.builddir == os.path.join('/', 'some', 'path', 'buildstream', 'build'))
    assert(context.artifactdir == os.path.join('/', 'some', 'path', 'buildstream', 'artifacts'))
    assert(context.logdir == os.path.join('/', 'some', 'path', 'buildstream', 'logs'))

    # Reset the environment variable
    del os.environ['XDG_CACHE_HOME']


# Test that values in a user specified config file
# override the defaults
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_user_config(context_fixture, datafiles):
    context = context_fixture['context']
    cache_home = context_fixture['xdg-cache']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'userconf.yaml')
    context.load(conf_file)

    assert(context.sourcedir == os.path.expanduser('~/pony'))
    assert(context.builddir == os.path.join(cache_home, 'buildstream', 'build'))
    assert(context.artifactdir == os.path.join(cache_home, 'buildstream', 'artifacts'))
    assert(context.logdir == os.path.join(cache_home, 'buildstream', 'logs'))


#######################################
#          Test failure modes         #
#######################################
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_missing_config(context_fixture, datafiles):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'nonexistant.yaml')

    with pytest.raises(LoadError) as exc:
        context.load(conf_file)

    assert (exc.value.reason == LoadErrorReason.MISSING_FILE)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_malformed_config(context_fixture, datafiles):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'malformed.yaml')

    with pytest.raises(LoadError) as exc:
        context.load(conf_file)

    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_notdict_config(context_fixture, datafiles):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'notdict.yaml')

    with pytest.raises(LoadError) as exc:
        context.load(conf_file)

    # XXX Should this be a different LoadErrorReason ?
    assert (exc.value.reason == LoadErrorReason.INVALID_YAML)
