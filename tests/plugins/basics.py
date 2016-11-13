import os
import pytest

from pluginbase import PluginBase
from buildstream._elementfactory import _ElementFactory
from buildstream._sourcefactory import _SourceFactory
from buildstream import PluginError

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'basics',
)

# Simple fixture to create a PluginBase object that
# we use for loading plugins.
@pytest.fixture()
def plugin_fixture(datafiles):
    return {
        'base' : PluginBase(package='buildstream.plugins')
    }

##############################################################
# Basics: test the fixture, test we can create the factories #
##############################################################
def test_fixture(plugin_fixture):
    assert(isinstance(plugin_fixture['base'], PluginBase))

def test_source_factory(plugin_fixture):
    factory = _SourceFactory(plugin_fixture['base'])
    assert(isinstance(factory, _SourceFactory))

def test_element_factory(plugin_fixture):
    factory = _ElementFactory(plugin_fixture['base'])
    assert(isinstance(factory, _ElementFactory))

##############################################################
#      Check that we can load custom sources & elements      #
##############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customsource'))
def test_custom_source(plugin_fixture, datafiles):
    factory = _SourceFactory(plugin_fixture['base'],
                             [ os.path.join(datafiles.dirname, datafiles.basename) ])
    assert(isinstance(factory, _SourceFactory))

    foo_type = factory.lookup('foo')
    assert(foo_type.__name__ == 'FooSource')

@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customelement'))
def test_custom_element(plugin_fixture, datafiles):
    factory = _ElementFactory(plugin_fixture['base'],
                             [ os.path.join(datafiles.dirname, datafiles.basename) ])
    assert(isinstance(factory, _ElementFactory))

    foo_type = factory.lookup('foo')
    assert(foo_type.__name__ == 'FooElement')

##############################################################
#            Check plugin loading failure modes              #
##############################################################
def test_missing_source(plugin_fixture):
    factory = _SourceFactory(plugin_fixture['base'])
    assert(isinstance(factory, _SourceFactory))

    # Test fails if PluginError is not raised
    with pytest.raises(PluginError) as exc:
        foo_type = factory.lookup('foo')

def test_missing_element(plugin_fixture):
    factory = _ElementFactory(plugin_fixture['base'])
    assert(isinstance(factory, _ElementFactory))

    # Test fails if PluginError is not raised
    with pytest.raises(PluginError) as exc:
        foo_type = factory.lookup('foo')

# Load one factory with 2 plugin directories both containing a foo plugin
@pytest.mark.datafiles(DATA_DIR)
def test_conflict_source(plugin_fixture, datafiles):
    plugins1 = os.path.join(datafiles.dirname, datafiles.basename, 'customsource')
    plugins2 = os.path.join(datafiles.dirname, datafiles.basename, 'anothersource')

    with pytest.raises(PluginError) as exc:
        factory = _SourceFactory(plugin_fixture['base'], [ plugins1, plugins2 ])

# Load one factory with 2 plugin directories both containing a foo plugin
@pytest.mark.datafiles(DATA_DIR)
def test_conflict_element(plugin_fixture, datafiles):
    plugins1 = os.path.join(datafiles.dirname, datafiles.basename, 'customelement')
    plugins2 = os.path.join(datafiles.dirname, datafiles.basename, 'anotherelement')

    with pytest.raises(PluginError) as exc:
        factory = _ElementFactory(plugin_fixture['base'], [ plugins1, plugins2 ])

# Load a factory with a plugin that returns a value instead of a Source subclass
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'notatype'))
def test_source_notatype(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = _SourceFactory(plugin_fixture['base'],
                                  [ os.path.join(datafiles.dirname, datafiles.basename) ])

# Load a factory with a plugin that returns a value instead of a Element subclass
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'notatype'))
def test_element_notatype(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = _ElementFactory(plugin_fixture['base'],
                                  [ os.path.join(datafiles.dirname, datafiles.basename) ])
