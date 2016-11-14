import os
import pytest

from buildstream import Context
from buildstream import ContextError

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)

# Simple fixture to create a PluginBase object that
# we use for loading plugins.
@pytest.fixture()
def context_fixture():
    return {
        'context' : Context('x86_64')
    }

#######################################
#        Test instantiation           #
#######################################
def test_context_create(context_fixture):
    context = context_fixture['context']
    assert(isinstance(context, Context))
    assert(context.arch == 'x86_64')

#######################################
#     Test configuration loading      #
#######################################
def test_context_load(context_fixture):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    context.load()
    assert(context.sourcedir == '~/buildstream/sources')
    assert(context.builddir == '~/buildstream/build')
    assert(context.deploydir == '~/buildstream/deploy')
    assert(context.artifactdir == '~/buildstream/artifacts')
    assert(context.ccachedir == '~/buildstream/ccache')

# Test that values in a user specified config file
# override the defaults
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_user_config(context_fixture, datafiles):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'userconf.yaml')
    context.load(conf_file)

    assert(context.sourcedir == '~/pony')
    assert(context.builddir == '~/buildstream/build')
    assert(context.deploydir == '~/buildstream/deploy')
    assert(context.artifactdir == '~/buildstream/artifacts')
    assert(context.ccachedir == '~/buildstream/ccache')

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

    with pytest.raises(ContextError) as exc:
        context.load(conf_file)

@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_malformed_config(context_fixture, datafiles):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'malformed.yaml')

    with pytest.raises(ContextError) as exc:
        context.load(conf_file)

@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_context_load_notdict_config(context_fixture, datafiles):
    context = context_fixture['context']
    assert(isinstance(context, Context))

    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'notdict.yaml')

    with pytest.raises(ContextError) as exc:
        context.load(conf_file)
