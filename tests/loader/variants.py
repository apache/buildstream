import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'variants',
)


##############################################################
#                 Test Basic Failure Modes                   #
##############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_variant_not_list(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variants-not-list.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_variant_unnamed(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/unnamed-variant.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_variant_bad_name(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variant-bad-name.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_variant_only_one(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/only-one-variant.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_variant_illegal_composite(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/variant-illegal-composite.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.ILLEGAL_COMPOSITE)


##############################################################
#                Test Simple Variant Compositing             #
##############################################################
@pytest.mark.datafiles(DATA_DIR)
def test_variant_simple_composite_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/simple-variant-compositing.bst', None, None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Without specifying a variant, the default (first) should have been chosen
    assert(element.config.get('somedata') == 5)
    assert(element.config.get('pony-color') == 'pink')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_simple_composite_pink_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/simple-variant-compositing.bst', 'pink', None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # We explicitly asked for the pink variation of this pony
    assert(element.config.get('somedata') == 5)
    assert(element.config.get('pony-color') == 'pink')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_simple_composite_blue_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/simple-variant-compositing.bst', 'blue', None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # We explicitly asked for the blue variation of this pony,
    # which has the side effect of overriding the value of 'somedata'
    assert(element.config.get('somedata') == 6)
    assert(element.config.get('pony-color') == 'blue')


##############################################################
#               Test Variant Dependency Plotting             #
##############################################################
#
# Convenience for asserting dependencies
#
def assert_dependency(element, index, name, key, value):

    # Test that the dependency we got is the pink color by default
    assert(len(element.dependencies) >= index + 1)
    dep = element.dependencies[index]

    assert(isinstance(dep, MetaElement))
    assert(dep.name == name)
    assert(isinstance(dep.config, dict))
    assert(dep.config.get(key) == value)

    return dep


@pytest.mark.datafiles(DATA_DIR)
def test_variant_simple_dependency_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/simple-dependency-variants.bst', None, None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Test that the default is a pink pony
    assert_dependency(element, 0, 'elements/simply-pink.bst', 'color', 'pink')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_simple_dependency_pink_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/simple-dependency-variants.bst', 'pink', None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Test that the explicit pink dependency is correct
    assert_dependency(element, 0, 'elements/simply-pink.bst', 'color', 'pink')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_simple_dependency_blue_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/simple-dependency-variants.bst', 'blue', None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Test that the explicit blue dependency is correct
    assert_dependency(element, 0, 'elements/simply-blue.bst', 'color', 'blue')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_indirect_dependency_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/indirect-dependency-variants.bst', None, None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Test that the default is a blue pony-color by default
    simple = assert_dependency(
        element, 0, 'elements/simple-dependency-variants.bst', 'pony-color', 'blue')

    # Test that the element we depend on now depends on the blue color
    assert_dependency(simple, 0, 'elements/simply-blue.bst', 'color', 'blue')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_indirect_dependency_blue_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/indirect-dependency-variants.bst', 'blue', None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Test for a blue pony-color
    simple = assert_dependency(
        element, 0, 'elements/simple-dependency-variants.bst', 'pony-color', 'blue')

    # Test that the element we depend on now depends on the blue color
    assert_dependency(simple, 0, 'elements/simply-blue.bst', 'color', 'blue')


@pytest.mark.datafiles(DATA_DIR)
def test_variant_indirect_dependency_pink_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(
        basedir, 'elements/indirect-dependency-variants.bst', 'pink', None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'pony')

    # Test for a blue pony-color
    simple = assert_dependency(
        element, 0, 'elements/simple-dependency-variants.bst', 'pony-color', 'pink')

    # Test that the element we depend on now depends on the blue color
    assert_dependency(simple, 0, 'elements/simply-pink.bst', 'color', 'pink')


@pytest.mark.datafiles(DATA_DIR)
def test_engine_resolve_agreement(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/tricky.bst', None, None)
    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'tricky')

    # Test the first dependency
    first = assert_dependency(element, 0, 'elements/tricky-first.bst', 'choice', 'second')
    second = assert_dependency(element, 1, 'elements/tricky-second.bst', 'choice', 'second')


@pytest.mark.datafiles(DATA_DIR)
def test_engine_disagreement(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/disagreement.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.VARIANT_DISAGREEMENT)
