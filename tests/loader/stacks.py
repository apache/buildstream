import os
import pytest

from buildstream import LoadError, LoadErrorReason
from buildstream._loader import Loader
from buildstream._metaelement import MetaElement

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'stacks',
)


@pytest.mark.datafiles(DATA_DIR)
def test_stack_basic(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    filename = os.path.join('elements', 'stack.bst')
    loader = Loader(basedir, filename, None, 'x86_64')

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')

    # Assert that the stuff from the include got into the element data,
    # first check that we depend on both elements
    assert(len(element.dependencies) == 2)

    pony = element.dependencies[0]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')

    horse = element.dependencies[1]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_dependencies(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    filename = os.path.join('elements', 'stackdepends.bst')
    loader = Loader(basedir, filename, None, 'x86_64')

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')

    # Assert that the stuff from the include got into the element data,
    # first check that we depend on both elements
    assert(len(element.dependencies) == 3)

    leaf = element.dependencies[0]
    assert(isinstance(leaf, MetaElement))
    assert(leaf.kind == 'element')

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')
    assert(len(pony.dependencies) == 1)

    # By virtue of being embedded in a stack which
    # depends on the leaf 'element', this element
    # also depends on the leaf 'element'
    ponyleaf = pony.dependencies[0]
    assert(isinstance(ponyleaf, MetaElement))
    assert(ponyleaf.kind == 'element')

    horse = element.dependencies[2]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')
    assert(len(horse.dependencies) == 1)

    # By virtue of being embedded in a stack which
    # depends on the leaf 'element', this element
    # also depends on the leaf 'element'
    horseleaf = horse.dependencies[0]
    assert(isinstance(horseleaf, MetaElement))
    assert(horseleaf.kind == 'element')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_includes(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/includingstack.bst', None, None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')

    # Assert that the stuff from the include got into the element data,
    # first check that we depend on both elements
    assert(len(element.dependencies) == 2)

    pony = element.dependencies[0]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')

    horse = element.dependencies[1]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')

    # Now check that the config data from the includes made it in
    assert(pony.config.get('pony') == 'Someone rides their pony')
    assert(horse.config.get('horse') == 'Riding a horse')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_arch_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/archstack.bst', None, None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'archstack')

    # Only one dependency, no known arch was selected
    assert(len(element.dependencies) == 1)
    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_arch_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/archstack.bst', None, 'x86_64')

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'archstack')

    # Two dependencies for x86_64
    assert(len(element.dependencies) == 2)
    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_arch_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/archstack.bst', None, 'x86_32')

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'archstack')

    # Two dependencies for x86_64
    assert(len(element.dependencies) == 2)
    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')

    horse = element.dependencies[1]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_nested_arch_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/nestedarchstack.bst', None, None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'nestedarchstack')

    # No specified arch, the color remains brown by default
    assert(len(element.dependencies) == 1)
    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')
    assert(rider.config.get('color') == 'brown')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_nested_arch_x86_64(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/nestedarchstack.bst', None, 'x86_64')

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'nestedarchstack')

    # x86_64, the color is now pink
    assert(len(element.dependencies) == 1)
    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')
    assert(rider.config.get('color') == 'pink')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_nested_arch_x86_32(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/nestedarchstack.bst', None, 'x86_32')

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'nestedarchstack')

    # x86_32, the color is now pink
    assert(len(element.dependencies) == 1)
    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')
    assert(rider.config.get('color') == 'blue')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_variant_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variantstack.bst', None, None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'variantstack')

    # No specified variant, we get a pony by default
    assert(len(element.dependencies) == 2)

    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_variant_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variantstack.bst', 'pony', None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'variantstack')

    # We asked for the pony variant, we get a pony
    assert(len(element.dependencies) == 2)

    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_variant_horse(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/variantstack.bst', 'horse', None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'variantstack')

    # We asked for the horse variant, we get a horse
    assert(len(element.dependencies) == 2)

    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')

    horse = element.dependencies[1]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')


@pytest.mark.datafiles(DATA_DIR)
def test_stack_nested_variant_default(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/nestedvariantstack.bst', None, None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'nestedvariantstack')

    # No specified variant, we get a pony by default
    assert(len(element.dependencies) == 3)

    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')
    assert(rider.config.get('number') == 6)

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')
    assert(pony.config.get('number') == 6)

    horse = element.dependencies[2]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')
    assert(horse.config.get('number') == 5)


@pytest.mark.datafiles(DATA_DIR)
def test_stack_nested_variant_pony(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/nestedvariantstack.bst', 'pony', None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'nestedvariantstack')

    # We asked for a pony, we get a pony
    assert(len(element.dependencies) == 3)

    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')
    assert(rider.config.get('number') == 6)

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')
    assert(pony.config.get('number') == 6)

    horse = element.dependencies[2]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')
    assert(horse.config.get('number') == 5)


@pytest.mark.datafiles(DATA_DIR)
def test_stack_nested_variant_horse(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/nestedvariantstack.bst', 'horse', None)

    element = loader.load()

    assert(isinstance(element, MetaElement))
    assert(element.kind == 'stack')
    assert(element.name == 'nestedvariantstack')

    # We asked for a horse, we get a horse
    assert(len(element.dependencies) == 3)

    rider = element.dependencies[0]
    assert(isinstance(rider, MetaElement))
    assert(rider.kind == 'rider')
    assert(rider.config.get('number') == 7)

    pony = element.dependencies[1]
    assert(isinstance(pony, MetaElement))
    assert(pony.kind == 'pony')
    assert(pony.config.get('number') == 5)

    horse = element.dependencies[2]
    assert(isinstance(horse, MetaElement))
    assert(horse.kind == 'horsy')
    assert(horse.config.get('number') == 7)


@pytest.mark.datafiles(DATA_DIR)
def test_stack_internal_circular_dependency(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/circulardepstack.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.CIRCULAR_DEPENDENCY)


@pytest.mark.datafiles(DATA_DIR)
def test_stack_embedded_in_stack(datafiles):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    loader = Loader(basedir, 'elements/stackinstack.bst', None, None)

    with pytest.raises(LoadError) as exc:
        element = loader.load()

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)
