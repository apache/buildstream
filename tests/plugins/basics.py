import os
import pytest

from pluginbase import PluginBase
from buildstream._elementfactory import ElementFactory
from buildstream._sourcefactory import SourceFactory
from buildstream import PluginError

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'basics',
)


# Simple fixture to create a PluginBase object that
# we use for loading plugins.
@pytest.fixture()
def plugin_fixture():
    return {
        'base': PluginBase(package='buildstream.plugins')
    }


##############################################################
# Basics: test the fixture, test we can create the factories #
##############################################################
def test_fixture(plugin_fixture):
    assert(isinstance(plugin_fixture['base'], PluginBase))


def test_source_factory(plugin_fixture):
    factory = SourceFactory(plugin_fixture['base'])
    assert(isinstance(factory, SourceFactory))


def test_element_factory(plugin_fixture):
    factory = ElementFactory(plugin_fixture['base'])
    assert(isinstance(factory, ElementFactory))


##############################################################
#      Check that we can load custom sources & elements      #
##############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customsource'))
def test_custom_source(plugin_fixture, datafiles):
    factory = SourceFactory(plugin_fixture['base'],
                            [os.path.join(datafiles.dirname,
                                          datafiles.basename)])
    assert(isinstance(factory, SourceFactory))

    foo_type = factory.lookup('foo')
    assert(foo_type.__name__ == 'FooSource')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'customelement'))
def test_custom_element(plugin_fixture, datafiles):
    factory = ElementFactory(plugin_fixture['base'],
                             [os.path.join(datafiles.dirname,
                                           datafiles.basename)])
    assert(isinstance(factory, ElementFactory))

    foo_type = factory.lookup('foo')
    assert(foo_type.__name__ == 'FooElement')


##############################################################
#            Check plugin loading failure modes              #
##############################################################
def test_missing_source(plugin_fixture):
    factory = SourceFactory(plugin_fixture['base'])
    assert(isinstance(factory, SourceFactory))

    # Test fails if PluginError is not raised
    with pytest.raises(PluginError) as exc:
        foo_type = factory.lookup('foo')


def test_missing_element(plugin_fixture):
    factory = ElementFactory(plugin_fixture['base'])
    assert(isinstance(factory, ElementFactory))

    # Test fails if PluginError is not raised
    with pytest.raises(PluginError) as exc:
        foo_type = factory.lookup('foo')


# Load one factory with 2 plugin directories both containing a foo plugin
@pytest.mark.datafiles(DATA_DIR)
def test_conflict_source(plugin_fixture, datafiles):
    plugins1 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'customsource')
    plugins2 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'anothersource')

    with pytest.raises(PluginError) as exc:
        factory = SourceFactory(plugin_fixture['base'], [plugins1, plugins2])


# Load one factory with 2 plugin directories both containing a foo plugin
@pytest.mark.datafiles(DATA_DIR)
def test_conflict_element(plugin_fixture, datafiles):
    plugins1 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'customelement')
    plugins2 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'anotherelement')

    with pytest.raises(PluginError) as exc:
        factory = ElementFactory(plugin_fixture['base'], [plugins1, plugins2])


# Load a factory with a plugin that returns a value instead of Source subclass
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'notatype'))
def test_source_notatype(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = SourceFactory(plugin_fixture['base'],
                                [os.path.join(datafiles.dirname,
                                              datafiles.basename)])


# Load a factory with a plugin that returns a value instead of Element subclass
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'notatype'))
def test_element_notatype(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = ElementFactory(plugin_fixture['base'],
                                 [os.path.join(datafiles.dirname,
                                               datafiles.basename)])


# Load a factory with a plugin that returns a type
# which is not a Source subclass
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'wrongtype'))
def test_source_wrongtype(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = SourceFactory(plugin_fixture['base'],
                                [os.path.join(datafiles.dirname,
                                              datafiles.basename)])


# Load a factory with a plugin that returns a type
# which is not a Element subclass
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'wrongtype'))
def test_element_wrongtype(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = ElementFactory(plugin_fixture['base'],
                                 [os.path.join(datafiles.dirname,
                                               datafiles.basename)])


# Load a factory with a plugin which fails to provide a setup() function
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'nosetup'))
def test_source_missing_setup(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = SourceFactory(plugin_fixture['base'],
                                [os.path.join(datafiles.dirname,
                                              datafiles.basename)])


# Load a factory with a plugin which fails to provide a setup() function
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'nosetup'))
def test_element_missing_setup(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = ElementFactory(plugin_fixture['base'],
                                 [os.path.join(datafiles.dirname,
                                               datafiles.basename)])


# Load a factory with a plugin which provides a setup symbol
# that is not a function
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badsetup'))
def test_source_bad_setup(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = SourceFactory(plugin_fixture['base'],
                                [os.path.join(datafiles.dirname,
                                              datafiles.basename)])


# Load a factory with a plugin which provides a setup symbol
# that is not a function
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'badsetup'))
def test_element_bad_setup(plugin_fixture, datafiles):
    with pytest.raises(PluginError) as exc:
        factory = ElementFactory(plugin_fixture['base'],
                                 [os.path.join(datafiles.dirname,
                                               datafiles.basename)])


##############################################################
#      Check we can load different contexts of plugin        #
##############################################################

# Load two factories, both of which define a different 'foo' plugin
@pytest.mark.datafiles(DATA_DIR)
def test_source_multicontext(plugin_fixture, datafiles):
    plugins1 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'customsource')
    plugins2 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'anothersource')

    factory1 = SourceFactory(plugin_fixture['base'], [plugins1])
    factory2 = SourceFactory(plugin_fixture['base'], [plugins2])
    assert(isinstance(factory1, SourceFactory))
    assert(isinstance(factory2, SourceFactory))

    foo_type1 = factory1.lookup('foo')
    foo_type2 = factory2.lookup('foo')
    assert(foo_type1.__name__ == 'FooSource')
    assert(foo_type2.__name__ == 'AnotherFooSource')


# Load two factories, both of which define a different 'foo' plugin
@pytest.mark.datafiles(DATA_DIR)
def test_element_multicontext(plugin_fixture, datafiles):
    plugins1 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'customelement')
    plugins2 = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'anotherelement')

    factory1 = ElementFactory(plugin_fixture['base'], [plugins1])
    factory2 = ElementFactory(plugin_fixture['base'], [plugins2])
    assert(isinstance(factory1, ElementFactory))
    assert(isinstance(factory2, ElementFactory))

    foo_type1 = factory1.lookup('foo')
    foo_type2 = factory2.lookup('foo')
    assert(foo_type1.__name__ == 'FooElement')
    assert(foo_type2.__name__ == 'AnotherFooElement')
