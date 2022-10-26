#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import os
from io import StringIO

import pytest

from buildstream import _yaml, Node, MappingNode, ProvenanceInformation, SequenceNode
from buildstream.exceptions import LoadErrorReason
from buildstream._exceptions import LoadError


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "yaml",
)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_load_yaml(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    loaded = _yaml.load(filename, shortname=None)
    assert loaded.get_str("kind") == "pony"


def assert_provenance(filename, line, col, node):
    provenance = node.get_provenance()

    assert isinstance(provenance, ProvenanceInformation)

    assert provenance._shortname == filename
    assert provenance._line == line
    assert provenance._col == col


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_basic_provenance(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    loaded = _yaml.load(filename, shortname=None)
    assert loaded.get_str("kind") == "pony"

    assert_provenance(filename, 1, 0, loaded)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_member_provenance(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    loaded = _yaml.load(filename, shortname=None)
    assert loaded.get_str("kind") == "pony"
    assert_provenance(filename, 2, 13, loaded.get_scalar("description"))


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_element_provenance(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    loaded = _yaml.load(filename, shortname=None)
    assert loaded.get_str("kind") == "pony"
    assert_provenance(filename, 5, 2, loaded.get_sequence("moods").scalar_at(1))


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_mapping_validate_keys(datafiles):

    valid = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")
    invalid = os.path.join(datafiles.dirname, datafiles.basename, "invalid.yaml")

    base = _yaml.load(valid, shortname=None)

    base.validate_keys(["kind", "description", "moods", "children", "extra"])

    base = _yaml.load(invalid, shortname=None)

    with pytest.raises(LoadError) as exc:
        base.validate_keys(["kind", "description", "moods", "children", "extra"])

    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_get(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    base = _yaml.load(filename, shortname=None)
    assert base.get_str("kind") == "pony"

    children = base.get_sequence("children")
    assert isinstance(children, SequenceNode)
    assert len(children) == 7

    child = base.get_sequence("children").mapping_at(6)
    assert_provenance(filename, 20, 8, child.get_scalar("mood"))

    extra = base.get_mapping("extra")
    with pytest.raises(LoadError) as exc:
        extra.get_mapping("old")

    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_set(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    base = _yaml.load(filename, shortname=None)

    assert "mother" not in base
    base["mother"] = "snow white"
    assert base.get_str("mother") == "snow white"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_set_overwrite(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    base = _yaml.load(filename, shortname=None)

    # Overwrite a string
    assert base.get_str("kind") == "pony"
    base["kind"] = "cow"
    assert base.get_str("kind") == "cow"

    # Overwrite a list as a string
    assert base.get_str_list("moods") == ["happy", "sad"]
    base["moods"] = "unemotional"
    assert base.get_str("moods") == "unemotional"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_set_list_element(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")

    base = _yaml.load(filename, shortname=None)

    assert base.get_str_list("moods") == ["happy", "sad"]
    base.get_sequence("moods")[0] = "confused"

    assert base.get_str_list("moods") == ["confused", "sad"]


# Really this is testing _yaml.node_copy(), we want to
# be sure that compositing values still preserves the original
# values in the copied dict.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_composite_preserve_originals(datafiles):

    filename = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")
    overlayfile = os.path.join(datafiles.dirname, datafiles.basename, "composite.yaml")

    base = _yaml.load(filename, shortname=None)
    overlay = _yaml.load(overlayfile, shortname=None)
    base_copy = base.clone()
    overlay._composite(base_copy)

    copy_extra = base_copy.get_mapping("extra")
    orig_extra = base.get_mapping("extra")

    # Test that the node copy has the overridden value...
    assert copy_extra.get_str("old") == "override"

    # But the original node is not effected by the override.
    assert orig_extra.get_str("old") == "new"


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
@pytest.mark.parametrize(
    "filename,index,length,mood,prov_file,prov_line,prov_col",
    [
        # Test results of compositing with the (<) prepend directive
        ("listprepend.yaml", 0, 9, "prepended1", "listprepend.yaml", 5, 10),
        ("listprepend.yaml", 1, 9, "prepended2", "listprepend.yaml", 7, 10),
        ("listprepend.yaml", 2, 9, "silly", "basics.yaml", 8, 8),
        ("listprepend.yaml", 8, 9, "sleepy", "basics.yaml", 20, 8),
        # Test results of compositing with the (>) append directive
        ("listappend.yaml", 7, 9, "appended1", "listappend.yaml", 5, 10),
        ("listappend.yaml", 8, 9, "appended2", "listappend.yaml", 7, 10),
        ("listappend.yaml", 0, 9, "silly", "basics.yaml", 8, 8),
        ("listappend.yaml", 6, 9, "sleepy", "basics.yaml", 20, 8),
        # Test results of compositing with both (<) and (>) directives
        ("listappendprepend.yaml", 0, 11, "prepended1", "listappendprepend.yaml", 5, 10),
        ("listappendprepend.yaml", 1, 11, "prepended2", "listappendprepend.yaml", 7, 10),
        ("listappendprepend.yaml", 2, 11, "silly", "basics.yaml", 8, 8),
        ("listappendprepend.yaml", 8, 11, "sleepy", "basics.yaml", 20, 8),
        ("listappendprepend.yaml", 9, 11, "appended1", "listappendprepend.yaml", 10, 10),
        ("listappendprepend.yaml", 10, 11, "appended2", "listappendprepend.yaml", 12, 10),
        # Test results of compositing with the (=) overwrite directive
        ("listoverwrite.yaml", 0, 2, "overwrite1", "listoverwrite.yaml", 5, 10),
        ("listoverwrite.yaml", 1, 2, "overwrite2", "listoverwrite.yaml", 7, 10),
        # Test results of compositing without any directive, implicitly overwriting
        ("implicitoverwrite.yaml", 0, 2, "overwrite1", "implicitoverwrite.yaml", 4, 8),
        ("implicitoverwrite.yaml", 1, 2, "overwrite2", "implicitoverwrite.yaml", 6, 8),
    ],
)
def test_list_composition(datafiles, filename, tmpdir, index, length, mood, prov_file, prov_line, prov_col):
    base_file = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")
    overlay_file = os.path.join(datafiles.dirname, datafiles.basename, filename)

    base = _yaml.load(base_file, shortname="basics.yaml")
    overlay = _yaml.load(overlay_file, shortname=filename)

    overlay._composite(base)

    children = base.get_sequence("children")
    assert len(children) == length
    child = children.mapping_at(index)

    assert child.get_str("mood") == mood
    assert_provenance(prov_file, prov_line, prov_col, child.get_node("mood"))


# Test that overwriting a list with an empty list works as expected.
@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_list_deletion(datafiles):
    base = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")
    overlay = os.path.join(datafiles.dirname, datafiles.basename, "listoverwriteempty.yaml")

    base = _yaml.load(base, shortname="basics.yaml")
    overlay = _yaml.load(overlay, shortname="listoverwriteempty.yaml")
    overlay._composite(base)

    children = base.get_sequence("children")
    assert not children


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
@pytest.mark.parametrize(
    "filename1,filename2,index,length,mood,prov_file,prov_line,prov_col",
    [
        # Test results of compositing literal list with (>) and then (<)
        ("listprepend.yaml", "listappend.yaml", 0, 11, "prepended1", "listprepend.yaml", 5, 10),
        ("listprepend.yaml", "listappend.yaml", 1, 11, "prepended2", "listprepend.yaml", 7, 10),
        ("listprepend.yaml", "listappend.yaml", 2, 11, "silly", "basics.yaml", 8, 8),
        ("listprepend.yaml", "listappend.yaml", 8, 11, "sleepy", "basics.yaml", 20, 8),
        ("listprepend.yaml", "listappend.yaml", 9, 11, "appended1", "listappend.yaml", 5, 10),
        ("listprepend.yaml", "listappend.yaml", 10, 11, "appended2", "listappend.yaml", 7, 10),
        # Test results of compositing literal list with (<) and then (>)
        ("listappend.yaml", "listprepend.yaml", 0, 11, "prepended1", "listprepend.yaml", 5, 10),
        ("listappend.yaml", "listprepend.yaml", 1, 11, "prepended2", "listprepend.yaml", 7, 10),
        ("listappend.yaml", "listprepend.yaml", 2, 11, "silly", "basics.yaml", 8, 8),
        ("listappend.yaml", "listprepend.yaml", 8, 11, "sleepy", "basics.yaml", 20, 8),
        ("listappend.yaml", "listprepend.yaml", 9, 11, "appended1", "listappend.yaml", 5, 10),
        ("listappend.yaml", "listprepend.yaml", 10, 11, "appended2", "listappend.yaml", 7, 10),
        # Test results of compositing literal list with (>) and then (>)
        ("listappend.yaml", "secondappend.yaml", 0, 11, "silly", "basics.yaml", 8, 8),
        ("listappend.yaml", "secondappend.yaml", 6, 11, "sleepy", "basics.yaml", 20, 8),
        ("listappend.yaml", "secondappend.yaml", 7, 11, "appended1", "listappend.yaml", 5, 10),
        ("listappend.yaml", "secondappend.yaml", 8, 11, "appended2", "listappend.yaml", 7, 10),
        ("listappend.yaml", "secondappend.yaml", 9, 11, "secondappend1", "secondappend.yaml", 5, 10),
        ("listappend.yaml", "secondappend.yaml", 10, 11, "secondappend2", "secondappend.yaml", 7, 10),
        # Test results of compositing literal list with (>) and then (>)
        ("listprepend.yaml", "secondprepend.yaml", 0, 11, "secondprepend1", "secondprepend.yaml", 5, 10),
        ("listprepend.yaml", "secondprepend.yaml", 1, 11, "secondprepend2", "secondprepend.yaml", 7, 10),
        ("listprepend.yaml", "secondprepend.yaml", 2, 11, "prepended1", "listprepend.yaml", 5, 10),
        ("listprepend.yaml", "secondprepend.yaml", 3, 11, "prepended2", "listprepend.yaml", 7, 10),
        ("listprepend.yaml", "secondprepend.yaml", 4, 11, "silly", "basics.yaml", 8, 8),
        ("listprepend.yaml", "secondprepend.yaml", 10, 11, "sleepy", "basics.yaml", 20, 8),
        # Test results of compositing literal list with (>) or (<) and then another literal list
        ("listappend.yaml", "implicitoverwrite.yaml", 0, 2, "overwrite1", "implicitoverwrite.yaml", 4, 8),
        ("listappend.yaml", "implicitoverwrite.yaml", 1, 2, "overwrite2", "implicitoverwrite.yaml", 6, 8),
        ("listprepend.yaml", "implicitoverwrite.yaml", 0, 2, "overwrite1", "implicitoverwrite.yaml", 4, 8),
        ("listprepend.yaml", "implicitoverwrite.yaml", 1, 2, "overwrite2", "implicitoverwrite.yaml", 6, 8),
        # Test results of compositing literal list with (>) or (<) and then an explicit (=) overwrite
        ("listappend.yaml", "listoverwrite.yaml", 0, 2, "overwrite1", "listoverwrite.yaml", 5, 10),
        ("listappend.yaml", "listoverwrite.yaml", 1, 2, "overwrite2", "listoverwrite.yaml", 7, 10),
        ("listprepend.yaml", "listoverwrite.yaml", 0, 2, "overwrite1", "listoverwrite.yaml", 5, 10),
        ("listprepend.yaml", "listoverwrite.yaml", 1, 2, "overwrite2", "listoverwrite.yaml", 7, 10),
        # Test results of compositing literal list an explicit overwrite (=) and then with (>) or (<)
        ("listoverwrite.yaml", "listappend.yaml", 0, 4, "overwrite1", "listoverwrite.yaml", 5, 10),
        ("listoverwrite.yaml", "listappend.yaml", 1, 4, "overwrite2", "listoverwrite.yaml", 7, 10),
        ("listoverwrite.yaml", "listappend.yaml", 2, 4, "appended1", "listappend.yaml", 5, 10),
        ("listoverwrite.yaml", "listappend.yaml", 3, 4, "appended2", "listappend.yaml", 7, 10),
        ("listoverwrite.yaml", "listprepend.yaml", 0, 4, "prepended1", "listprepend.yaml", 5, 10),
        ("listoverwrite.yaml", "listprepend.yaml", 1, 4, "prepended2", "listprepend.yaml", 7, 10),
        ("listoverwrite.yaml", "listprepend.yaml", 2, 4, "overwrite1", "listoverwrite.yaml", 5, 10),
        ("listoverwrite.yaml", "listprepend.yaml", 3, 4, "overwrite2", "listoverwrite.yaml", 7, 10),
    ],
)
def test_list_composition_twice(
    datafiles, tmpdir, filename1, filename2, index, length, mood, prov_file, prov_line, prov_col
):
    file_base = os.path.join(datafiles.dirname, datafiles.basename, "basics.yaml")
    file1 = os.path.join(datafiles.dirname, datafiles.basename, filename1)
    file2 = os.path.join(datafiles.dirname, datafiles.basename, filename2)

    #####################
    # Round 1 - Fight !
    #####################
    base = _yaml.load(file_base, shortname="basics.yaml")
    overlay1 = _yaml.load(file1, shortname=filename1)
    overlay2 = _yaml.load(file2, shortname=filename2)

    overlay1._composite(base)
    overlay2._composite(base)

    children = base.get_sequence("children")
    assert len(children) == length
    child = children.mapping_at(index)

    assert child.get_str("mood") == mood
    assert_provenance(prov_file, prov_line, prov_col, child.get_node("mood"))

    #####################
    # Round 2 - Fight !
    #####################
    base = _yaml.load(file_base, shortname="basics.yaml")
    overlay1 = _yaml.load(file1, shortname=filename1)
    overlay2 = _yaml.load(file2, shortname=filename2)

    overlay2._composite(overlay1)
    overlay1._composite(base)

    children = base.get_sequence("children")
    assert len(children) == length
    child = children.mapping_at(index)

    assert child.get_str("mood") == mood
    assert_provenance(prov_file, prov_line, prov_col, child.get_node("mood"))


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_convert_value_to_string(datafiles):
    conf_file = os.path.join(datafiles.dirname, datafiles.basename, "convert_value_to_str.yaml")

    # Run file through yaml to convert it
    test_dict = _yaml.load(conf_file, shortname=None)

    user_config = test_dict.get_str("Test1")
    assert isinstance(user_config, str)
    assert user_config == "1_23_4"

    user_config = test_dict.get_str("Test2")
    assert isinstance(user_config, str)
    assert user_config == "1.23.4"

    user_config = test_dict.get_str("Test3")
    assert isinstance(user_config, str)
    assert user_config == "1.20"

    user_config = test_dict.get_str("Test4")
    assert isinstance(user_config, str)
    assert user_config == "OneTwoThree"


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_value_doesnt_match_expected(datafiles):
    conf_file = os.path.join(datafiles.dirname, datafiles.basename, "convert_value_to_str.yaml")

    # Run file through yaml to convert it
    test_dict = _yaml.load(conf_file, shortname=None)

    with pytest.raises(LoadError) as exc:
        test_dict.get_int("Test4")
    assert exc.value.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_roundtrip_dump(datafiles):
    filename = os.path.join(datafiles.dirname, datafiles.basename, "roundtrip-test.yaml")
    with open(filename, "r", encoding="utf-8") as fh:
        rt_raw = fh.read()

    rt_loaded = _yaml.roundtrip_load(filename)

    # Now walk the loaded data structure, checking for ints etc.
    def walk_node(node):
        for v in node.values():
            if isinstance(v, list):
                walk_list(v)
            elif isinstance(v, dict):
                walk_node(v)
            else:
                assert isinstance(v, str)

    def walk_list(l):
        for v in l:
            if isinstance(v, list):
                walk_list(v)
            elif isinstance(v, dict):
                walk_node(v)
            else:
                assert isinstance(v, str)

    walk_node(rt_loaded)

    outfile = StringIO()
    _yaml.roundtrip_dump(rt_loaded, file=outfile)
    rt_back = outfile.getvalue()

    assert rt_raw == rt_back


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize(
    "case",
    [
        ["a", "b", "c"],
        ["foo", 1],
        ["stuff", 0, "colour"],
        ["bird", 0, 1],
    ],
)
def test_node_find_target(datafiles, case):
    filename = os.path.join(datafiles.dirname, datafiles.basename, "traversal.yaml")
    # We set copy_tree in order to ensure that the nodes in `loaded`
    # are not the same nodes as in `prov.toplevel`
    loaded = _yaml.load(filename, shortname=None, copy_tree=True)

    prov = loaded.get_provenance()

    toplevel = prov._toplevel

    assert toplevel is not loaded

    # Walk down the node tree, with insider knowledge of how nodes are
    # laid out.  Client code should never do this.
    def _walk(node, entry, rest):
        if rest:
            if isinstance(entry, int):
                new_node = node.node_at(entry)
            else:
                new_node = node.get_node(entry)

            return _walk(new_node, rest[0], rest[1:])
        else:
            if isinstance(entry, int):
                return node.node_at(entry)
            return node.get_node(entry)

    want = _walk(loaded, case[0], case[1:])
    found_path = toplevel._find(want)

    assert case == found_path


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_node_find_target_fails(datafiles):
    filename = os.path.join(datafiles.dirname, datafiles.basename, "traversal.yaml")
    loaded = _yaml.load(filename, shortname=None, copy_tree=True)

    brand_new = Node.from_dict({})

    assert loaded._find(brand_new) is None


@pytest.mark.datafiles(os.path.join(DATA_DIR))
@pytest.mark.parametrize(
    "filename, provenance",
    [
        ("list-of-dict.yaml", "list-of-dict.yaml [line 2 column 2]"),
        ("list-of-list.yaml", "list-of-list.yaml [line 2 column 2]"),
    ],
    ids=["list-of-dict", "list-of-list"],
)
def test_get_str_list_invalid(datafiles, filename, provenance):
    conf_file = os.path.join(datafiles.dirname, datafiles.basename, filename)

    base = _yaml.load(conf_file, shortname=None)

    with pytest.raises(LoadError) as exc:
        base.get_str_list("list")
    assert exc.value.reason == LoadErrorReason.INVALID_DATA
    assert provenance in str(exc.value)


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_get_str_list_default_none(datafiles):
    conf_file = os.path.join(datafiles.dirname, datafiles.basename, "list-of-dict.yaml")

    base = _yaml.load(conf_file, shortname=None)

    # There is no "pony" key here, assert that the default return is smooth
    strings = base.get_str_list("pony", None)
    assert strings is None


@pytest.mark.datafiles(os.path.join(DATA_DIR))
def test_mapping_node_assign_none(datafiles):
    conf_file = os.path.join(datafiles.dirname, datafiles.basename, "dictionary.yaml")
    dump_file = os.path.join(datafiles.dirname, datafiles.basename, "dictionary-dump.yaml")

    base = _yaml.load(conf_file, shortname=None)
    nested = base.get_mapping("nested")
    nested["ref"] = None

    # Check that we have successfully set the ref to None
    value = nested.get_scalar("ref")
    assert value.is_none()

    # Without saving and loading, our None value is retained in memory
    stripped = base.strip_node_info()
    assert stripped["nested"]["ref"] is None

    # Save and load
    _yaml.roundtrip_dump(base, dump_file)
    loaded = _yaml.load(dump_file, shortname=None)
    loaded_nested = loaded.get_mapping("nested")
    value = loaded_nested.get_scalar("ref")

    # The loaded value will be an empty string, because we don't recognize None
    # value representations in YAML
    assert value.as_str() == ""
