import os
import pytest
from collections import Mapping

from buildstream import _yaml
from buildstream import LoadError, LoadErrorReason
from buildstream._yaml import CompositePolicy

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_load_yaml(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')

    loaded = _yaml.load(filename)
    assert(loaded.get('kind') == 'pony')


def assert_provenance(filename, line, col, node, key=None, indices=[]):
    provenance = _yaml.node_get_provenance(node, key=key, indices=indices)

    if key:
        if indices:
            assert(isinstance(provenance, _yaml.ElementProvenance))
        else:
            assert(isinstance(provenance, _yaml.MemberProvenance))
    else:
        assert(isinstance(provenance, _yaml.DictProvenance))

    assert(provenance.filename == filename)
    assert(provenance.line == line)
    assert(provenance.col == col)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_basic_provenance(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')

    loaded = _yaml.load(filename)
    assert(loaded.get('kind') == 'pony')

    assert_provenance(filename, 1, 0, loaded)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_member_provenance(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')

    loaded = _yaml.load(filename)
    assert(loaded.get('kind') == 'pony')
    assert_provenance(filename, 2, 13, loaded, 'description')


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_element_provenance(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')

    loaded = _yaml.load(filename)
    assert(loaded.get('kind') == 'pony')
    assert_provenance(filename, 5, 2, loaded, 'moods', [1])


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_composited_overwrite_provenance(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')
    overlayfile = os.path.join(datafiles.dirname,
                               datafiles.basename,
                               'composite.yaml')

    base = _yaml.load(filename)
    assert(base.get('kind') == 'pony')
    assert_provenance(filename, 1, 0, base)

    overlay = _yaml.load(overlayfile)
    assert(overlay.get('kind') == 'horse')
    assert_provenance(overlayfile, 1, 0, overlay)

    _yaml.composite_dict(base, overlay,
                         policy=CompositePolicy.OVERWRITE, typesafe=True)
    assert(base.get('kind') == 'horse')

    children = base.get('children')
    assert(isinstance(children, list))
    assert(len(children) == 1)

    assert_provenance(filename, 1, 0, base)

    # The entire children member is overwritten with the overlay
    assert_provenance(overlayfile, 4, 0, base, 'children')
    assert_provenance(overlayfile, 4, 2, base, 'children', [0])

    # The child dict itself has the overlay provenance
    child = children[0]
    assert_provenance(overlayfile, 5, 8, child, 'mood')


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_composited_array_append_provenance(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')
    overlayfile = os.path.join(datafiles.dirname,
                               datafiles.basename,
                               'composite.yaml')

    base = _yaml.load(filename)
    assert(base.get('kind') == 'pony')
    assert_provenance(filename, 1, 0, base)

    overlay = _yaml.load(overlayfile)
    assert(overlay.get('kind') == 'horse')
    assert_provenance(overlayfile, 1, 0, overlay)

    _yaml.composite_dict(base, overlay,
                         policy=CompositePolicy.ARRAY_APPEND, typesafe=True)
    assert(base.get('kind') == 'horse')

    children = base.get('children')
    assert(isinstance(children, list))
    assert(len(children) == 8)

    assert_provenance(filename, 1, 0, base)
    assert_provenance(filename, 7, 0, base, 'children')

    # The newly added element has the overlay provenance
    assert_provenance(overlayfile, 4, 2, base, 'children', [7])

    # The child dict itself has the overlay provenance
    child = children[7]
    assert_provenance(overlayfile, 5, 8, child, 'mood')

    extra = base.get('extra')
    assert(isinstance(extra, dict))
    another = extra.get('another')
    assert(isinstance(another, dict))

    assert_provenance(filename, 22, 2, base, 'extra')
    assert_provenance(filename, 22, 2, extra)
    assert_provenance(filename, 22, 8, extra, 'this')

    assert_provenance(overlayfile, 9, 4, extra, 'another')
    assert_provenance(overlayfile, 9, 4, another)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_validate_node(datafiles):

    valid = os.path.join(datafiles.dirname,
                         datafiles.basename,
                         'basics.yaml')
    invalid = os.path.join(datafiles.dirname,
                           datafiles.basename,
                           'invalid.yaml')

    base = _yaml.load(valid)

    _yaml.validate_node(base, ['kind', 'description', 'moods', 'children', 'extra'])

    base = _yaml.load(invalid)

    with pytest.raises(LoadError) as exc:
        _yaml.validate_node(base, ['kind', 'description', 'moods', 'children', 'extra'])

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_get(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')
    overlayfile = os.path.join(datafiles.dirname,
                               datafiles.basename,
                               'composite.yaml')

    base = _yaml.load(filename)
    assert(base.get('kind') == 'pony')
    overlay = _yaml.load(overlayfile)
    assert(overlay.get('kind') == 'horse')
    _yaml.composite_dict(base, overlay,
                         policy=CompositePolicy.ARRAY_APPEND,
                         typesafe=True)
    assert(base.get('kind') == 'horse')

    children = _yaml.node_get(base, list, 'children')
    assert(isinstance(children, list))
    assert(len(children) == 8)

    child = _yaml.node_get(base, Mapping, 'children', indices=[7])
    assert_provenance(overlayfile, 5, 8, child, 'mood')

    extra = _yaml.node_get(base, Mapping, 'extra')
    another = _yaml.node_get(extra, Mapping, 'another')

    with pytest.raises(LoadError) as exc:
        wrong = _yaml.node_get(another, Mapping, 'five')

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


# Really this is testing _yaml.node_chain_copy(), we want to
# be sure that when using a ChainMap copy, compositing values
# still preserves the original values in the copied dict.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_composite_preserve_originals(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')
    overlayfile = os.path.join(datafiles.dirname,
                               datafiles.basename,
                               'composite.yaml')

    base = _yaml.load(filename)
    overlay = _yaml.load(overlayfile)
    base_copy = _yaml.node_chain_copy(base)
    _yaml.composite_dict(base_copy, overlay,
                         policy=CompositePolicy.OVERWRITE, typesafe=True)

    copy_extra = _yaml.node_get(base_copy, Mapping, 'extra')
    orig_extra = _yaml.node_get(base, Mapping, 'extra')

    # Test that the node copy has the overridden value...
    assert(_yaml.node_get(copy_extra, str, 'old') == 'override')

    # But the original node is not effected by the override.
    assert(_yaml.node_get(orig_extra, str, 'old') == 'new')
