import os
import pytest

from buildstream import InvocationContext

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)

# Simple fixture to create a PluginBase object that
# we use for loading plugins.
@pytest.fixture()
def context_fixture():
    return {
        'context' : InvocationContext('x86_64')
    }

#######################################
#        Test instantiation           #
#######################################
def test_context_create(context_fixture):
    context = context_fixture['context']
    assert(isinstance(context, InvocationContext))
    assert(context.arch == 'x86_64')

#######################################
#     Test configuration loading      #
#######################################
def test_context_load(context_fixture):
    context = context_fixture['context']
    assert(isinstance(context, InvocationContext))

    context.load()
    assert(context.sourcedir == '~/buildstream/sources')
    assert(context.builddir == '~/buildstream/build')
    assert(context.deploydir == '~/buildstream/deploy')
    assert(context.artifactdir == '~/buildstream/artifacts')
    assert(context.ccachedir == '~/buildstream/ccache')
