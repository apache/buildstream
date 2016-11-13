import pytest

from pluginbase import PluginBase
from buildstream._elementfactory import _ElementFactory
from buildstream._sourcefactory import _SourceFactory

@pytest.fixture()
def plugin_base():
    base = PluginBase(package='buildstream.plugins')
    return base

def test_fixture(plugin_base):
    assert(isinstance (plugin_base, PluginBase))

def test_source_factory(plugin_base):
    source_factory = _SourceFactory(plugin_base)
    assert(isinstance (source_factory, _SourceFactory))

def test_element_factory(plugin_base):
    element_factory = _ElementFactory(plugin_base)
    assert(isinstance (element_factory, _ElementFactory))
