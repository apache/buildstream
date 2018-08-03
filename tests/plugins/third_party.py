import os
import pytest

from pluginbase import PluginBase
from buildstream._elementfactory import ElementFactory
from buildstream._sourcefactory import SourceFactory

from tests.testutils.setuptools import entry_fixture

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'third_party'
)


# Simple fixture to create a PluginBase object that
# we use for loading plugins.
@pytest.fixture()
def plugin_fixture():
    return {
        'base': PluginBase(package='buildstream.plugins')
    }


##################################################################
#                              Tests                             #
##################################################################
# Test that external element plugin loading works.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'third_party_element'))
def test_custom_pip_element(plugin_fixture, entry_fixture, datafiles):
    origin_data = [{
        'origin': 'local',
        'path': str(datafiles),
        'plugins': {'foop': 0}
    }]
    factory = ElementFactory(plugin_fixture['base'],
                             plugin_origins=origin_data)
    assert(isinstance(factory, ElementFactory))

    entry_fixture(datafiles, 'buildstream.plugins', 'third_party_element:foop')

    foo_type, _ = factory.lookup('foop')
    assert(foo_type.__name__ == 'FooElement')


# Test that external source plugin loading works.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'third_party_source'))
def test_custom_pip_source(plugin_fixture, entry_fixture, datafiles):
    origin_data = [{
        'origin': 'local',
        'path': str(datafiles),
        'plugins': {'foop': 0}
    }]
    factory = SourceFactory(plugin_fixture['base'],
                            plugin_origins=origin_data)
    assert(isinstance(factory, SourceFactory))

    entry_fixture(datafiles, 'buildstream.plugins', 'third_party_source:foop')

    foo_type, _ = factory.lookup('foop')
    assert(foo_type.__name__ == 'FooSource')
