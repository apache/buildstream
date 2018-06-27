import os
import pytest
from collections import Mapping

from buildstream import _yaml
from buildstream._exceptions import LoadError, LoadErrorReason

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

    assert(provenance.filename.shortname == filename)
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
def test_node_validate(datafiles):

    valid = os.path.join(datafiles.dirname,
                         datafiles.basename,
                         'basics.yaml')
    invalid = os.path.join(datafiles.dirname,
                           datafiles.basename,
                           'invalid.yaml')

    base = _yaml.load(valid)

    _yaml.node_validate(base, ['kind', 'description', 'moods', 'children', 'extra'])

    base = _yaml.load(invalid)

    with pytest.raises(LoadError) as exc:
        _yaml.node_validate(base, ['kind', 'description', 'moods', 'children', 'extra'])

    assert (exc.value.reason == LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_get(datafiles):

    filename = os.path.join(datafiles.dirname,
                            datafiles.basename,
                            'basics.yaml')

    base = _yaml.load(filename)
    assert(base.get('kind') == 'pony')

    children = _yaml.node_get(base, list, 'children')
    assert(isinstance(children, list))
    assert(len(children) == 7)

    child = _yaml.node_get(base, Mapping, 'children', indices=[6])
    assert_provenance(filename, 20, 8, child, 'mood')

    extra = _yaml.node_get(base, Mapping, 'extra')
    with pytest.raises(LoadError) as exc:
        wrong = _yaml.node_get(extra, Mapping, 'old')

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
    _yaml.composite_dict(base_copy, overlay)

    copy_extra = _yaml.node_get(base_copy, Mapping, 'extra')
    orig_extra = _yaml.node_get(base, Mapping, 'extra')

    # Test that the node copy has the overridden value...
    assert(_yaml.node_get(copy_extra, str, 'old') == 'override')

    # But the original node is not effected by the override.
    assert(_yaml.node_get(orig_extra, str, 'old') == 'new')


# Tests for list composition
#
# Each test composits a filename on top of basics.yaml, and tests
# the toplevel children list at the specified index
#
# Parameters:
#    filename: The file to composite on top of basics.yaml
#    index: The index in the children list
#    length: The expected length of the children list
#    mood: The expected value of the mood attribute of the dictionary found at index in children
#    prov_file: The expected provenance filename of "mood"
#    prov_line: The expected provenance line of "mood"
#    prov_col: The expected provenance column of "mood"
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("filename,index,length,mood,prov_file,prov_line,prov_col", [

    # Test results of compositing with the (<) prepend directive
    ('listprepend.yaml', 0, 9, 'prepended1', 'listprepend.yaml', 5, 10),
    ('listprepend.yaml', 1, 9, 'prepended2', 'listprepend.yaml', 7, 10),
    ('listprepend.yaml', 2, 9, 'silly', 'basics.yaml', 8, 8),
    ('listprepend.yaml', 8, 9, 'sleepy', 'basics.yaml', 20, 8),

    # Test results of compositing with the (>) append directive
    ('listappend.yaml', 7, 9, 'appended1', 'listappend.yaml', 5, 10),
    ('listappend.yaml', 8, 9, 'appended2', 'listappend.yaml', 7, 10),
    ('listappend.yaml', 0, 9, 'silly', 'basics.yaml', 8, 8),
    ('listappend.yaml', 6, 9, 'sleepy', 'basics.yaml', 20, 8),

    # Test results of compositing with both (<) and (>) directives
    ('listappendprepend.yaml', 0, 11, 'prepended1', 'listappendprepend.yaml', 5, 10),
    ('listappendprepend.yaml', 1, 11, 'prepended2', 'listappendprepend.yaml', 7, 10),
    ('listappendprepend.yaml', 2, 11, 'silly', 'basics.yaml', 8, 8),
    ('listappendprepend.yaml', 8, 11, 'sleepy', 'basics.yaml', 20, 8),
    ('listappendprepend.yaml', 9, 11, 'appended1', 'listappendprepend.yaml', 10, 10),
    ('listappendprepend.yaml', 10, 11, 'appended2', 'listappendprepend.yaml', 12, 10),

    # Test results of compositing with the (=) overwrite directive
    ('listoverwrite.yaml', 0, 2, 'overwrite1', 'listoverwrite.yaml', 5, 10),
    ('listoverwrite.yaml', 1, 2, 'overwrite2', 'listoverwrite.yaml', 7, 10),

    # Test results of compositing without any directive, implicitly overwriting
    ('implicitoverwrite.yaml', 0, 2, 'overwrite1', 'implicitoverwrite.yaml', 4, 8),
    ('implicitoverwrite.yaml', 1, 2, 'overwrite2', 'implicitoverwrite.yaml', 6, 8),
])
def test_list_composition(datafiles, filename,
                          index, length, mood,
                          prov_file, prov_line, prov_col):
    base = os.path.join(datafiles.dirname, datafiles.basename, 'basics.yaml')
    overlay = os.path.join(datafiles.dirname, datafiles.basename, filename)

    base = _yaml.load(base, shortname='basics.yaml')
    overlay = _yaml.load(overlay, shortname=filename)
    _yaml.composite_dict(base, overlay)

    children = _yaml.node_get(base, list, 'children')
    assert len(children) == length
    child = children[index]

    assert child['mood'] == mood
    assert_provenance(prov_file, prov_line, prov_col, child, 'mood')


# Test that overwriting a list with an empty list works as expected.
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_list_deletion(datafiles):
    base = os.path.join(datafiles.dirname, datafiles.basename, 'basics.yaml')
    overlay = os.path.join(datafiles.dirname, datafiles.basename, 'listoverwriteempty.yaml')

    base = _yaml.load(base, shortname='basics.yaml')
    overlay = _yaml.load(overlay, shortname='listoverwriteempty.yaml')
    _yaml.composite_dict(base, overlay)

    children = _yaml.node_get(base, list, 'children')
    assert len(children) == 0


# Tests for deep list composition
#
# Same as test_list_composition(), but adds an additional file
# in between so that lists are composited twice.
#
# This test will to two iterations for each parameter
# specification, expecting the same results
#
#   First iteration:
#      composited = basics.yaml & filename1
#      composited = composited & filename2
#
#   Second iteration:
#      composited = filename1 & filename2
#      composited = basics.yaml & composited
#
# Parameters:
#    filename1: The file to composite on top of basics.yaml
#    filename2: The file to composite on top of filename1
#    index: The index in the children list
#    length: The expected length of the children list
#    mood: The expected value of the mood attribute of the dictionary found at index in children
#    prov_file: The expected provenance filename of "mood"
#    prov_line: The expected provenance line of "mood"
#    prov_col: The expected provenance column of "mood"
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize("filename1,filename2,index,length,mood,prov_file,prov_line,prov_col", [

    # Test results of compositing literal list with (>) and then (<)
    ('listprepend.yaml', 'listappend.yaml', 0, 11, 'prepended1', 'listprepend.yaml', 5, 10),
    ('listprepend.yaml', 'listappend.yaml', 1, 11, 'prepended2', 'listprepend.yaml', 7, 10),
    ('listprepend.yaml', 'listappend.yaml', 2, 11, 'silly', 'basics.yaml', 8, 8),
    ('listprepend.yaml', 'listappend.yaml', 8, 11, 'sleepy', 'basics.yaml', 20, 8),
    ('listprepend.yaml', 'listappend.yaml', 9, 11, 'appended1', 'listappend.yaml', 5, 10),
    ('listprepend.yaml', 'listappend.yaml', 10, 11, 'appended2', 'listappend.yaml', 7, 10),

    # Test results of compositing literal list with (<) and then (>)
    ('listappend.yaml', 'listprepend.yaml', 0, 11, 'prepended1', 'listprepend.yaml', 5, 10),
    ('listappend.yaml', 'listprepend.yaml', 1, 11, 'prepended2', 'listprepend.yaml', 7, 10),
    ('listappend.yaml', 'listprepend.yaml', 2, 11, 'silly', 'basics.yaml', 8, 8),
    ('listappend.yaml', 'listprepend.yaml', 8, 11, 'sleepy', 'basics.yaml', 20, 8),
    ('listappend.yaml', 'listprepend.yaml', 9, 11, 'appended1', 'listappend.yaml', 5, 10),
    ('listappend.yaml', 'listprepend.yaml', 10, 11, 'appended2', 'listappend.yaml', 7, 10),

    # Test results of compositing literal list with (>) and then (>)
    ('listappend.yaml', 'secondappend.yaml', 0, 11, 'silly', 'basics.yaml', 8, 8),
    ('listappend.yaml', 'secondappend.yaml', 6, 11, 'sleepy', 'basics.yaml', 20, 8),
    ('listappend.yaml', 'secondappend.yaml', 7, 11, 'appended1', 'listappend.yaml', 5, 10),
    ('listappend.yaml', 'secondappend.yaml', 8, 11, 'appended2', 'listappend.yaml', 7, 10),
    ('listappend.yaml', 'secondappend.yaml', 9, 11, 'secondappend1', 'secondappend.yaml', 5, 10),
    ('listappend.yaml', 'secondappend.yaml', 10, 11, 'secondappend2', 'secondappend.yaml', 7, 10),

    # Test results of compositing literal list with (>) and then (>)
    ('listprepend.yaml', 'secondprepend.yaml', 0, 11, 'secondprepend1', 'secondprepend.yaml', 5, 10),
    ('listprepend.yaml', 'secondprepend.yaml', 1, 11, 'secondprepend2', 'secondprepend.yaml', 7, 10),
    ('listprepend.yaml', 'secondprepend.yaml', 2, 11, 'prepended1', 'listprepend.yaml', 5, 10),
    ('listprepend.yaml', 'secondprepend.yaml', 3, 11, 'prepended2', 'listprepend.yaml', 7, 10),
    ('listprepend.yaml', 'secondprepend.yaml', 4, 11, 'silly', 'basics.yaml', 8, 8),
    ('listprepend.yaml', 'secondprepend.yaml', 10, 11, 'sleepy', 'basics.yaml', 20, 8),

    # Test results of compositing literal list with (>) or (<) and then another literal list
    ('listappend.yaml', 'implicitoverwrite.yaml', 0, 2, 'overwrite1', 'implicitoverwrite.yaml', 4, 8),
    ('listappend.yaml', 'implicitoverwrite.yaml', 1, 2, 'overwrite2', 'implicitoverwrite.yaml', 6, 8),
    ('listprepend.yaml', 'implicitoverwrite.yaml', 0, 2, 'overwrite1', 'implicitoverwrite.yaml', 4, 8),
    ('listprepend.yaml', 'implicitoverwrite.yaml', 1, 2, 'overwrite2', 'implicitoverwrite.yaml', 6, 8),

    # Test results of compositing literal list with (>) or (<) and then an explicit (=) overwrite
    ('listappend.yaml', 'listoverwrite.yaml', 0, 2, 'overwrite1', 'listoverwrite.yaml', 5, 10),
    ('listappend.yaml', 'listoverwrite.yaml', 1, 2, 'overwrite2', 'listoverwrite.yaml', 7, 10),
    ('listprepend.yaml', 'listoverwrite.yaml', 0, 2, 'overwrite1', 'listoverwrite.yaml', 5, 10),
    ('listprepend.yaml', 'listoverwrite.yaml', 1, 2, 'overwrite2', 'listoverwrite.yaml', 7, 10),

    # Test results of compositing literal list an explicit overwrite (=) and then with (>) or (<)
    ('listoverwrite.yaml', 'listappend.yaml', 0, 4, 'overwrite1', 'listoverwrite.yaml', 5, 10),
    ('listoverwrite.yaml', 'listappend.yaml', 1, 4, 'overwrite2', 'listoverwrite.yaml', 7, 10),
    ('listoverwrite.yaml', 'listappend.yaml', 2, 4, 'appended1', 'listappend.yaml', 5, 10),
    ('listoverwrite.yaml', 'listappend.yaml', 3, 4, 'appended2', 'listappend.yaml', 7, 10),
    ('listoverwrite.yaml', 'listprepend.yaml', 0, 4, 'prepended1', 'listprepend.yaml', 5, 10),
    ('listoverwrite.yaml', 'listprepend.yaml', 1, 4, 'prepended2', 'listprepend.yaml', 7, 10),
    ('listoverwrite.yaml', 'listprepend.yaml', 2, 4, 'overwrite1', 'listoverwrite.yaml', 5, 10),
    ('listoverwrite.yaml', 'listprepend.yaml', 3, 4, 'overwrite2', 'listoverwrite.yaml', 7, 10),
])
def test_list_composition_twice(datafiles, filename1, filename2,
                                index, length, mood,
                                prov_file, prov_line, prov_col):
    file_base = os.path.join(datafiles.dirname, datafiles.basename, 'basics.yaml')
    file1 = os.path.join(datafiles.dirname, datafiles.basename, filename1)
    file2 = os.path.join(datafiles.dirname, datafiles.basename, filename2)

    #####################
    # Round 1 - Fight !
    #####################
    base = _yaml.load(file_base, shortname='basics.yaml')
    overlay1 = _yaml.load(file1, shortname=filename1)
    overlay2 = _yaml.load(file2, shortname=filename2)

    _yaml.composite_dict(base, overlay1)
    _yaml.composite_dict(base, overlay2)

    children = _yaml.node_get(base, list, 'children')
    assert len(children) == length
    child = children[index]

    assert child['mood'] == mood
    assert_provenance(prov_file, prov_line, prov_col, child, 'mood')

    #####################
    # Round 2 - Fight !
    #####################
    base = _yaml.load(file_base, shortname='basics.yaml')
    overlay1 = _yaml.load(file1, shortname=filename1)
    overlay2 = _yaml.load(file2, shortname=filename2)

    _yaml.composite_dict(overlay1, overlay2)
    _yaml.composite_dict(base, overlay1)

    children = _yaml.node_get(base, list, 'children')
    assert len(children) == length
    child = children[index]

    assert child['mood'] == mood
    assert_provenance(prov_file, prov_line, prov_col, child, 'mood')


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_convert_value_to_string(datafiles):
    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'convert_value_to_str.yaml')

    # Run file through yaml to convert it
    test_dict = _yaml.load(conf_file)

    user_config = _yaml.node_get(test_dict, str, "Test1")
    assert isinstance(user_config, str)
    assert user_config == "1_23_4"

    user_config = _yaml.node_get(test_dict, str, "Test2")
    assert isinstance(user_config, str)
    assert user_config == "1.23.4"

    user_config = _yaml.node_get(test_dict, str, "Test3")
    assert isinstance(user_config, str)
    assert user_config == "1.20"

    user_config = _yaml.node_get(test_dict, str, "Test4")
    assert isinstance(user_config, str)
    assert user_config == "OneTwoThree"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_value_doesnt_match_expected(datafiles):
    conf_file = os.path.join(datafiles.dirname,
                             datafiles.basename,
                             'convert_value_to_str.yaml')

    # Run file through yaml to convert it
    test_dict = _yaml.load(conf_file)

    with pytest.raises(LoadError) as exc:
        user_config = _yaml.node_get(test_dict, int, "Test4")
    assert exc.value.reason == LoadErrorReason.INVALID_DATA
