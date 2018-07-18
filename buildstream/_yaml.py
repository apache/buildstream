#
#  Copyright (C) 2018 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import sys
import collections
import string
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path

from ruamel import yaml
from ruamel.yaml.representer import SafeRepresenter, RoundTripRepresenter
from ruamel.yaml.constructor import RoundTripConstructor
from ._exceptions import LoadError, LoadErrorReason

# This overrides the ruamel constructor to treat everything as a string
RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:int', RoundTripConstructor.construct_yaml_str)
RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:float', RoundTripConstructor.construct_yaml_str)

# We store information in the loaded yaml on a DictProvenance
# stored in all dictionaries under this key
PROVENANCE_KEY = '__bst_provenance_info'


# Provides information about file for provenance
#
# Args:
#    name (str): Full path to the file
#    shortname (str): Relative path to the file
#    project (Project): Project where the shortname is relative from
class ProvenanceFile():
    def __init__(self, name, shortname, project):
        self.name = name
        self.shortname = shortname
        self.project = project


# Provenance tracks the origin of a given node in the parsed dictionary.
#
# Args:
#   node (dict, list, value): A binding to the originally parsed value
#   filename (string): The filename the node was loaded from
#   toplevel (dict): The toplevel of the loaded file, suitable for later dumps
#   line (int): The line number where node was parsed
#   col (int): The column number where node was parsed
#
class Provenance():
    def __init__(self, filename, node, toplevel, line=0, col=0):
        self.filename = filename
        self.node = node
        self.toplevel = toplevel
        self.line = line
        self.col = col

    # Convert a Provenance to a string for error reporting
    def __str__(self):
        return "{} [line {:d} column {:d}]".format(self.filename.shortname, self.line, self.col)

    # Abstract method
    def clone(self):
        pass  # pragma: nocover


# A Provenance for dictionaries, these are stored in the copy of the
# loaded YAML tree and track the provenance of all members
#
class DictProvenance(Provenance):
    def __init__(self, filename, node, toplevel, line=None, col=None):

        if line is None or col is None:
            # Special case for loading an empty dict
            if hasattr(node, 'lc'):
                line = node.lc.line + 1
                col = node.lc.col
            else:
                line = 1
                col = 0

        super(DictProvenance, self).__init__(filename, node, toplevel, line=line, col=col)

        self.members = {}

    def clone(self):
        provenance = DictProvenance(self.filename, self.node, self.toplevel,
                                    line=self.line, col=self.col)

        provenance.members = {
            member_name: member.clone()
            for member_name, member in self.members.items()
        }
        return provenance


# A Provenance for dict members
#
class MemberProvenance(Provenance):
    def __init__(self, filename, parent_dict, member_name, toplevel,
                 node=None, line=None, col=None):

        if parent_dict is not None:
            node = parent_dict[member_name]
            line, col = parent_dict.lc.value(member_name)
            line += 1

        super(MemberProvenance, self).__init__(
            filename, node, toplevel, line=line, col=col)

        # Only used if member is a list
        self.elements = []

    def clone(self):
        provenance = MemberProvenance(self.filename, None, None, self.toplevel,
                                      node=self.node, line=self.line, col=self.col)
        provenance.elements = [e.clone() for e in self.elements]
        return provenance


# A Provenance for list elements
#
class ElementProvenance(Provenance):
    def __init__(self, filename, parent_list, index, toplevel,
                 node=None, line=None, col=None):

        if parent_list is not None:
            node = parent_list[index]
            line, col = parent_list.lc.item(index)
            line += 1

        super(ElementProvenance, self).__init__(
            filename, node, toplevel, line=line, col=col)

        # Only used if element is a list
        self.elements = []

    def clone(self):
        provenance = ElementProvenance(self.filename, None, None, self.toplevel,
                                       node=self.node, line=self.line, col=self.col)

        provenance.elements = [e.clone for e in self.elements]
        return provenance


# These exceptions are intended to be caught entirely within
# the BuildStream framework, hence they do not reside in the
# public exceptions.py
class CompositeError(Exception):
    def __init__(self, path, message):
        super(CompositeError, self).__init__(message)
        self.path = path


class CompositeTypeError(CompositeError):
    def __init__(self, path, expected_type, actual_type):
        super(CompositeTypeError, self).__init__(
            path,
            "Error compositing dictionary key '{}', expected source type '{}' "
            "but received type '{}'"
            .format(path, expected_type.__name__, actual_type.__name__))
        self.expected_type = expected_type
        self.actual_type = actual_type


# Loads a dictionary from some YAML
#
# Args:
#    filename (str): The YAML file to load
#    shortname (str): The filename in shorthand for error reporting (or None)
#    copy_tree (bool): Whether to make a copy, preserving the original toplevels
#                      for later serialization
#
# Returns (dict): A loaded copy of the YAML file with provenance information
#
# Raises: LoadError
#
def load(filename, shortname=None, copy_tree=False, *, project=None):
    if not shortname:
        shortname = filename

    file = ProvenanceFile(filename, shortname, project)

    try:
        with open(filename) as f:
            return load_data(f, file, copy_tree=copy_tree)
    except FileNotFoundError as e:
        raise LoadError(LoadErrorReason.MISSING_FILE,
                        "Could not find file at {}".format(filename)) from e
    except IsADirectoryError as e:
        raise LoadError(LoadErrorReason.LOADING_DIRECTORY,
                        "{} is a directory. bst command expects a .bst file."
                        .format(filename)) from e


# Like load(), but doesnt require the data to be in a file
#
def load_data(data, file=None, copy_tree=False):

    try:
        contents = yaml.load(data, yaml.loader.RoundTripLoader, preserve_quotes=True)
    except (yaml.scanner.ScannerError, yaml.composer.ComposerError, yaml.parser.ParserError) as e:
        raise LoadError(LoadErrorReason.INVALID_YAML,
                        "Malformed YAML:\n\n{}\n\n{}\n".format(e.problem, e.problem_mark)) from e

    if not isinstance(contents, dict):
        # Special case allowance for None, when the loaded file has only comments in it.
        if contents is None:
            contents = {}
        else:
            raise LoadError(LoadErrorReason.INVALID_YAML,
                            "YAML file has content of type '{}' instead of expected type 'dict': {}"
                            .format(type(contents).__name__, file.name))

    return node_decorated_copy(file, contents, copy_tree=copy_tree)


# Dumps a previously loaded YAML node to a file
#
# Args:
#    node (dict): A node previously loaded with _yaml.load() above
#    filename (str): The YAML file to load
#
def dump(node, filename=None):
    with ExitStack() as stack:
        if filename:
            from . import utils
            f = stack.enter_context(utils.save_file_atomic(filename, 'w'))
        else:
            f = sys.stdout
        yaml.round_trip_dump(node, f)


# node_decorated_copy()
#
# Create a copy of a loaded dict tree decorated with Provenance
# information, used directly after loading yaml
#
# Args:
#    filename (str): The filename
#    toplevel (node): The toplevel dictionary node
#    copy_tree (bool): Whether to load a copy and preserve the original
#
# Returns: A copy of the toplevel decorated with Provinance
#
def node_decorated_copy(filename, toplevel, copy_tree=False):
    if copy_tree:
        result = deepcopy(toplevel)
    else:
        result = toplevel

    node_decorate_dict(filename, result, toplevel, toplevel)

    return result


def node_decorate_dict(filename, target, source, toplevel):
    provenance = DictProvenance(filename, source, toplevel)
    target[PROVENANCE_KEY] = provenance

    for key, value in node_items(source):
        member = MemberProvenance(filename, source, key, toplevel)
        provenance.members[key] = member

        target_value = target.get(key)
        if isinstance(value, collections.Mapping):
            node_decorate_dict(filename, target_value, value, toplevel)
        elif isinstance(value, list):
            member.elements = node_decorate_list(filename, target_value, value, toplevel)


def node_decorate_list(filename, target, source, toplevel):

    elements = []

    for item in source:
        idx = source.index(item)
        target_item = target[idx]
        element = ElementProvenance(filename, source, idx, toplevel)

        if isinstance(item, collections.Mapping):
            node_decorate_dict(filename, target_item, item, toplevel)
        elif isinstance(item, list):
            element.elements = node_decorate_list(filename, target_item, item, toplevel)

        elements.append(element)

    return elements


# node_get_provenance()
#
# Gets the provenance for a node
#
# Args:
#   node (dict): a dictionary
#   key (str): key in the dictionary
#   indices (list of indexes): Index path, in the case of list values
#
# Returns: The Provenance of the dict, member or list element
#
def node_get_provenance(node, key=None, indices=None):

    provenance = node.get(PROVENANCE_KEY)
    if provenance and key:
        provenance = provenance.members.get(key)
        if provenance and indices is not None:
            for index in indices:
                provenance = provenance.elements[index]

    return provenance


# Helper to use utils.sentinel without unconditional utils import,
# which causes issues for completion.
#
# Local private, but defined here because sphinx appears to break if
# it's not defined before any functions calling it in default kwarg
# values.
#
def _get_sentinel():
    from .utils import _sentinel
    return _sentinel


# node_get()
#
# Fetches a value from a dictionary node and checks it for
# an expected value. Use default_value when parsing a value
# which is only optionally supplied.
#
# Args:
#    node (dict): The dictionary node
#    expected_type (type): The expected type for the value being searched
#    key (str): The key to get a value for in node
#    indices (list of ints): Optionally decend into lists of lists
#
# Returns:
#    The value if found in node, otherwise default_value is returned
#
# Raises:
#    LoadError, when the value found is not of the expected type
#
# Note:
#    Returned strings are stripped of leading and trailing whitespace
#
def node_get(node, expected_type, key, indices=None, default_value=_get_sentinel()):
    value = node.get(key, default_value)
    provenance = node_get_provenance(node)
    if value is _get_sentinel():
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "{}: Dictionary did not contain expected key '{}'".format(provenance, key))

    path = key
    if indices is not None:
        # Implied type check of the element itself
        value = node_get(node, list, key)
        for index in indices:
            value = value[index]
            path += '[{:d}]'.format(index)

    # We want to allow None as a valid value for any type
    if value is None:
        return None

    if not isinstance(value, expected_type):
        # Attempt basic conversions if possible, typically we want to
        # be able to specify numeric values and convert them to strings,
        # but we dont want to try converting dicts/lists
        try:
            if (expected_type == bool and isinstance(value, str)):
                # Dont coerce booleans to string, this makes "False" strings evaluate to True
                if value == 'true' or value == 'True':
                    value = True
                elif value == 'false' or value == 'False':
                    value = False
                else:
                    raise ValueError()
            elif not (expected_type == list or
                      expected_type == dict or
                      isinstance(value, (list, dict))):
                value = expected_type(value)
            else:
                raise ValueError()
        except (ValueError, TypeError):
            provenance = node_get_provenance(node, key=key, indices=indices)
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: Value of '{}' is not of the expected type '{}'"
                            .format(provenance, path, expected_type.__name__))

    # Trim it at the bud, let all loaded strings from yaml be stripped of whitespace
    if isinstance(value, str):
        value = value.strip()

    return value


# node_get_project_path()
#
# Fetches a project path from a dictionary node and validates it
#
# Paths are asserted to never lead to a directory outside of the project
# directory. In addition, paths can not point to symbolic links, fifos,
# sockets and block/character devices.
#
# The `check_is_file` and `check_is_dir` parameters can be used to
# perform additional validations on the path. Note that an exception
# will always be raised if both parameters are set to ``True``.
#
# Args:
#    node (dict): A dictionary loaded from YAML
#    key (str): The key whose value contains a path to validate
#    project_dir (str): The project directory
#    check_is_file (bool): If ``True`` an error will also be raised
#                          if path does not point to a regular file.
#                          Defaults to ``False``
#    check_is_dir (bool): If ``True`` an error will be also raised
#                         if path does not point to a directory.
#                         Defaults to ``False``
# Returns:
#    (str): The project path
#
# Raises:
#    (LoadError): In case that the project path is not valid or does not
#                 exist
#
def node_get_project_path(node, key, project_dir, *,
                          check_is_file=False, check_is_dir=False):
    path_str = node_get(node, str, key)
    path = Path(path_str)
    project_dir_path = Path(project_dir)

    provenance = node_get_provenance(node, key=key)

    if (project_dir_path / path).is_symlink():
        raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                        "{}: Specified path '{}' must not point to "
                        "symbolic links "
                        .format(provenance, path_str))

    if path.parts and path.parts[0] == '..':
        raise LoadError(LoadErrorReason.PROJ_PATH_INVALID,
                        "{}: Specified path '{}' first component must "
                        "not be '..'"
                        .format(provenance, path_str))

    try:
        if sys.version_info[0] == 3 and sys.version_info[1] < 6:
            full_resolved_path = (project_dir_path / path).resolve()
        else:
            full_resolved_path = (project_dir_path / path).resolve(strict=True)
    except FileNotFoundError:
        raise LoadError(LoadErrorReason.MISSING_FILE,
                        "{}: Specified path '{}' does not exist"
                        .format(provenance, path_str))

    is_inside = project_dir_path in full_resolved_path.parents or (
        full_resolved_path == project_dir_path)

    if path.is_absolute() or not is_inside:
        raise LoadError(LoadErrorReason.PROJ_PATH_INVALID,
                        "{}: Specified path '{}' must not lead outside of the "
                        "project directory"
                        .format(provenance, path_str))

    if full_resolved_path.is_socket() or (
            full_resolved_path.is_fifo() or
            full_resolved_path.is_block_device()):
        raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                        "{}: Specified path '{}' points to an unsupported "
                        "file kind"
                        .format(provenance, path_str))

    if check_is_file and not full_resolved_path.is_file():
        raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                        "{}: Specified path '{}' is not a regular file"
                        .format(provenance, path_str))

    if check_is_dir and not full_resolved_path.is_dir():
        raise LoadError(LoadErrorReason.PROJ_PATH_INVALID_KIND,
                        "{}: Specified path '{}' is not a directory"
                        .format(provenance, path_str))

    return path_str


# node_items()
#
# A convenience generator for iterating over loaded key/value
# tuples in a dictionary loaded from project YAML.
#
# Args:
#    node (dict): The dictionary node
#
# Yields:
#    (str): The key name
#    (anything): The value for the key
#
def node_items(node):
    for key, value in node.items():
        if key == PROVENANCE_KEY:
            continue
        yield (key, value)


# Gives a node a dummy provenance, in case of compositing dictionaries
# where the target is an empty {}
def ensure_provenance(node):
    provenance = node.get(PROVENANCE_KEY)
    if not provenance:
        provenance = DictProvenance(ProvenanceFile('', '', None), node, node)
    node[PROVENANCE_KEY] = provenance

    return provenance


# is_ruamel_str():
#
# Args:
#    value: A value loaded from ruamel
#
# This returns if the value is "stringish", since ruamel
# has some complex types to represent strings, this is needed
# to avoid compositing exceptions in order to allow various
# string types to be interchangable and acceptable
#
def is_ruamel_str(value):

    if isinstance(value, str):
        return True
    elif isinstance(value, yaml.scalarstring.ScalarString):
        return True

    return False


# is_composite_list
#
# Checks if the given node is a Mapping with array composition
# directives.
#
# Args:
#    node (value): Any node
#
# Returns:
#    (bool): True if node was a Mapping containing only
#            list composition directives
#
# Raises:
#    (LoadError): If node was a mapping and contained a mix of
#                 list composition directives and other keys
#
def is_composite_list(node):

    if isinstance(node, collections.Mapping):
        has_directives = False
        has_keys = False

        for key, _ in node_items(node):
            if key in ['(>)', '(<)', '(=)']:  # pylint: disable=simplifiable-if-statement
                has_directives = True
            else:
                has_keys = True

            if has_keys and has_directives:
                provenance = node_get_provenance(node)
                raise LoadError(LoadErrorReason.INVALID_DATA,
                                "{}: Dictionary contains array composition directives and arbitrary keys"
                                .format(provenance))
        return has_directives

    return False


# composite_list_prepend
#
# Internal helper for list composition
#
# Args:
#    target_node (dict): A simple dictionary
#    target_key (dict): The key indicating a literal array to prepend to
#    source_node (dict): Another simple dictionary
#    source_key (str): The key indicating an array to prepend to the target
#
# Returns:
#    (bool): True if a source list was found and compositing occurred
#
def composite_list_prepend(target_node, target_key, source_node, source_key):

    source_list = node_get(source_node, list, source_key, default_value=[])
    if not source_list:
        return False

    target_provenance = node_get_provenance(target_node)
    source_provenance = node_get_provenance(source_node)

    if target_node.get(target_key) is None:
        target_node[target_key] = []

    source_list = list_chain_copy(source_list)
    target_list = target_node[target_key]

    for element in reversed(source_list):
        target_list.insert(0, element)

    if not target_provenance.members.get(target_key):
        target_provenance.members[target_key] = source_provenance.members[source_key].clone()
    else:
        for p in reversed(source_provenance.members[source_key].elements):
            target_provenance.members[target_key].elements.insert(0, p.clone())

    return True


# composite_list_append
#
# Internal helper for list composition
#
# Args:
#    target_node (dict): A simple dictionary
#    target_key (dict): The key indicating a literal array to append to
#    source_node (dict): Another simple dictionary
#    source_key (str): The key indicating an array to append to the target
#
# Returns:
#    (bool): True if a source list was found and compositing occurred
#
def composite_list_append(target_node, target_key, source_node, source_key):

    source_list = node_get(source_node, list, source_key, default_value=[])
    if not source_list:
        return False

    target_provenance = node_get_provenance(target_node)
    source_provenance = node_get_provenance(source_node)

    if target_node.get(target_key) is None:
        target_node[target_key] = []

    source_list = list_chain_copy(source_list)
    target_list = target_node[target_key]

    target_list.extend(source_list)

    if not target_provenance.members.get(target_key):
        target_provenance.members[target_key] = source_provenance.members[source_key].clone()
    else:
        target_provenance.members[target_key].elements.extend([
            p.clone() for p in source_provenance.members[source_key].elements
        ])

    return True


# composite_list_overwrite
#
# Internal helper for list composition
#
# Args:
#    target_node (dict): A simple dictionary
#    target_key (dict): The key indicating a literal array to overwrite
#    source_node (dict): Another simple dictionary
#    source_key (str): The key indicating an array to overwrite the target with
#
# Returns:
#    (bool): True if a source list was found and compositing occurred
#
def composite_list_overwrite(target_node, target_key, source_node, source_key):

    # We need to handle the legitimate case of overwriting a list with an empty
    # list, hence the slightly odd default_value of [None] rather than [].
    source_list = node_get(source_node, list, source_key, default_value=[None])
    if source_list == [None]:
        return False

    target_provenance = node_get_provenance(target_node)
    source_provenance = node_get_provenance(source_node)

    target_node[target_key] = list_chain_copy(source_list)
    target_provenance.members[target_key] = source_provenance.members[source_key].clone()

    return True


# composite_list():
#
# Composite the source value onto the target value, if either
# sides are lists, or dictionaries containing list compositing directives
#
# Args:
#    target_node (dict): A simple dictionary
#    source_node (dict): Another simple dictionary
#    key (str): The key to compose on
#
# Returns:
#    (bool): True if both sides were logical lists
#
# Raises:
#    (LoadError): If one side was a logical list and the other was not
#
def composite_list(target_node, source_node, key):
    target_value = target_node.get(key)
    source_value = source_node[key]

    target_key_provenance = node_get_provenance(target_node, key)
    source_key_provenance = node_get_provenance(source_node, key)

    # Whenever a literal list is encountered in the source, it
    # overwrites the target values and provenance completely.
    #
    if isinstance(source_value, list):

        source_provenance = node_get_provenance(source_node)
        target_provenance = node_get_provenance(target_node)

        # Assert target type
        if not (target_value is None or
                isinstance(target_value, list) or
                is_composite_list(target_value)):
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: List cannot overwrite value at: {}"
                            .format(source_key_provenance, target_key_provenance))

        composite_list_overwrite(target_node, key, source_node, key)
        return True

    # When a composite list is encountered in the source, then
    # multiple outcomes can occur...
    #
    elif is_composite_list(source_value):

        # If there is nothing there, then the composite list
        # is copied in it's entirety as is, and preserved
        # for later composition
        #
        if target_value is None:
            source_provenance = node_get_provenance(source_node)
            target_provenance = node_get_provenance(target_node)

            target_node[key] = node_chain_copy(source_value)
            target_provenance.members[key] = source_provenance.members[key].clone()

        # If the target is a literal list, then composition
        # occurs directly onto that target, leaving the target
        # as a literal list to overwrite anything in later composition
        #
        elif isinstance(target_value, list):
            composite_list_overwrite(target_node, key, source_value, '(=)')
            composite_list_prepend(target_node, key, source_value, '(<)')
            composite_list_append(target_node, key, source_value, '(>)')

        # If the target is a composite list, then composition
        # occurs in the target composite list, and the composite
        # target list is preserved in dictionary form for further
        # composition.
        #
        elif is_composite_list(target_value):

            if composite_list_overwrite(target_value, '(=)', source_value, '(=)'):

                # When overwriting a target with composition directives, remove any
                # existing prepend/append directives in the target before adding our own
                target_provenance = node_get_provenance(target_value)

                for directive in ['(<)', '(>)']:
                    try:
                        del target_value[directive]
                        del target_provenance.members[directive]
                    except KeyError:
                        # Ignore errors from deletion of non-existing keys
                        pass

            # Prepend to the target prepend array, and append to the append array
            composite_list_prepend(target_value, '(<)', source_value, '(<)')
            composite_list_append(target_value, '(>)', source_value, '(>)')

        else:
            raise LoadError(LoadErrorReason.INVALID_DATA,
                            "{}: List cannot overwrite value at: {}"
                            .format(source_key_provenance, target_key_provenance))

        # We handled list composition in some way
        return True

    # Source value was not a logical list
    return False


# composite_dict():
#
# Composites values in target with values from source
#
# Args:
#    target (dict): A simple dictionary
#    source (dict): Another simple dictionary
#
# Raises: CompositeError
#
# Unlike the dictionary update() method, nested values in source
# will not obsolete entire subdictionaries in target, instead both
# dictionaries will be recursed and a composition of both will result
#
# This is useful for overriding configuration files and element
# configurations.
#
def composite_dict(target, source, path=None):
    target_provenance = ensure_provenance(target)
    source_provenance = ensure_provenance(source)

    for key, source_value in node_items(source):

        # Track the full path of keys, only for raising CompositeError
        if path:
            thispath = path + '.' + key
        else:
            thispath = key

        # Handle list composition separately
        if composite_list(target, source, key):
            continue

        target_value = target.get(key)

        if isinstance(source_value, collections.Mapping):

            # Handle creating new dicts on target side
            if target_value is None:
                target_value = {}
                target[key] = target_value

                # Give the new dict provenance
                value_provenance = source_value.get(PROVENANCE_KEY)
                if value_provenance:
                    target_value[PROVENANCE_KEY] = value_provenance.clone()

                # Add a new provenance member element to the containing dict
                target_provenance.members[key] = source_provenance.members[key]

            if not isinstance(target_value, collections.Mapping):
                raise CompositeTypeError(thispath, type(target_value), type(source_value))

            # Recurse into matching dictionary
            composite_dict(target_value, source_value, path=thispath)

        else:

            if target_value is not None:

                # Exception here: depending on how strings were declared ruamel may
                # use a different type, but for our purposes, any stringish type will do.
                if not (is_ruamel_str(source_value) and is_ruamel_str(target_value)) \
                   and not isinstance(source_value, type(target_value)):
                    raise CompositeTypeError(thispath, type(target_value), type(source_value))

            # Overwrite simple values, lists and mappings have already been handled
            target_provenance.members[key] = source_provenance.members[key].clone()
            target[key] = source_value


# Like composite_dict(), but raises an all purpose LoadError for convenience
#
def composite(target, source):
    assert hasattr(source, 'get')

    source_provenance = node_get_provenance(source)
    try:
        composite_dict(target, source)
    except CompositeTypeError as e:
        error_prefix = ""
        if source_provenance:
            error_prefix = "{}: ".format(source_provenance)
        raise LoadError(LoadErrorReason.ILLEGAL_COMPOSITE,
                        "{}Expected '{}' type for configuration '{}', instead received '{}'"
                        .format(error_prefix,
                                e.expected_type.__name__,
                                e.path,
                                e.actual_type.__name__)) from e


# SanitizedDict is an OrderedDict that is dumped as unordered mapping.
# This provides deterministic output for unordered mappings.
#
class SanitizedDict(collections.OrderedDict):
    pass


RoundTripRepresenter.add_representer(SanitizedDict,
                                     SafeRepresenter.represent_dict)


# node_sanitize()
#
# Returnes an alphabetically ordered recursive copy
# of the source node with internal provenance information stripped.
#
# Only dicts are ordered, list elements are left in order.
#
def node_sanitize(node):

    if isinstance(node, collections.Mapping):

        result = SanitizedDict()

        key_list = [key for key, _ in node_items(node)]
        for key in sorted(key_list):
            result[key] = node_sanitize(node[key])

        return result

    elif isinstance(node, list):
        return [node_sanitize(elt) for elt in node]

    return node


# node_validate()
#
# Validate the node so as to ensure the user has not specified
# any keys which are unrecognized by buildstream (usually this
# means a typo which would otherwise not trigger an error).
#
# Args:
#    node (dict): A dictionary loaded from YAML
#    valid_keys (list): A list of valid keys for the specified node
#
# Raises:
#    LoadError: In the case that the specified node contained
#               one or more invalid keys
#
def node_validate(node, valid_keys):

    # Probably the fastest way to do this: https://stackoverflow.com/a/23062482
    valid_keys = set(valid_keys)
    valid_keys.add(PROVENANCE_KEY)
    invalid = next((key for key in node if key not in valid_keys), None)

    if invalid:
        provenance = node_get_provenance(node, key=invalid)
        raise LoadError(LoadErrorReason.INVALID_DATA,
                        "{}: Unexpected key: {}".format(provenance, invalid))


# ChainMap
#
# This is a derivative of collections.ChainMap(), but supports
# explicit deletions of keys.
#
# The purpose of this is to create a virtual copy-on-write
# copy of a dictionary, so that mutating it in any way does
# not effect the underlying dictionaries.
#
# collections.ChainMap covers this already mostly, but fails
# to record internal state so as to hide keys which have been
# explicitly deleted.
#
class ChainMap(collections.ChainMap):

    def __init__(self, *maps):
        super().__init__(*maps)
        self.__deletions = set()

    def __getitem__(self, key):

        # Honor deletion state of 'key'
        if key in self.__deletions:
            return self.__missing__(key)

        return super().__getitem__(key)

    def __len__(self):
        return len(set().union(*self.maps) - self.__deletions)

    def __iter__(self):
        return iter(set().union(*self.maps) - self.__deletions)

    def __contains__(self, key):
        if key in self.__deletions:
            return False
        return any(key in m for m in self.maps)

    def __bool__(self):
        # Attempt to preserve 'any' optimization
        any_keys = any(self.maps)

        # Something existed, try again with deletions subtracted
        if any_keys:
            return any(set().union(*self.maps) - self.__deletions)

        return False

    def __setitem__(self, key, value):
        self.__deletions.discard(key)
        super().__setitem__(key, value)

    def __delitem__(self, key):
        if key in self.__deletions:
            raise KeyError('Key was already deleted from this mapping: {!r}'.format(key))

        # Ignore KeyError if it's not in the first map, just save the deletion state
        try:
            super().__delitem__(key)
        except KeyError:
            pass

        # Store deleted state
        self.__deletions.add(key)

    def popitem(self):
        poppable = set().union(*self.maps) - self.__deletions
        for key in poppable:
            return self.pop(key)

        raise KeyError('No keys found.')

    __marker = object()

    def pop(self, key, default=__marker):
        # Reimplement MutableMapping's behavior here
        try:
            value = self[key]
        except KeyError:
            if default is self.__marker:
                raise
            return default
        else:
            del self[key]
            return value

    def clear(self):
        clearable = set().union(*self.maps) - self.__deletions
        for key in clearable:
            del self[key]


def node_chain_copy(source):
    copy = ChainMap({}, source)
    for key, value in source.items():
        if isinstance(value, collections.Mapping):
            copy[key] = node_chain_copy(value)
        elif isinstance(value, list):
            copy[key] = list_chain_copy(value)
        elif isinstance(value, Provenance):
            copy[key] = value.clone()

    return copy


def list_chain_copy(source):
    copy = []
    for item in source:
        if isinstance(item, collections.Mapping):
            copy.append(node_chain_copy(item))
        elif isinstance(item, list):
            copy.append(list_chain_copy(item))
        elif isinstance(item, Provenance):
            copy.append(item.clone())
        else:
            copy.append(item)

    return copy


def node_copy(source):
    copy = {}
    for key, value in source.items():
        if isinstance(value, collections.Mapping):
            copy[key] = node_copy(value)
        elif isinstance(value, list):
            copy[key] = list_copy(value)
        elif isinstance(value, Provenance):
            copy[key] = value.clone()
        else:
            copy[key] = value

    ensure_provenance(copy)

    return copy


def list_copy(source):
    copy = []
    for item in source:
        if isinstance(item, collections.Mapping):
            copy.append(node_copy(item))
        elif isinstance(item, list):
            copy.append(list_copy(item))
        elif isinstance(item, Provenance):
            copy.append(item.clone())
        else:
            copy.append(item)

    return copy


# node_final_assertions()
#
# This must be called on a fully loaded and composited node,
# after all composition has completed.
#
# Args:
#    node (Mapping): The final composited node
#
# Raises:
#    (LoadError): If any assertions fail
#
def node_final_assertions(node):
    for key, value in node_items(node):

        # Assert that list composition directives dont remain, this
        # indicates that the user intended to override a list which
        # never existed in the underlying data
        #
        if key in ['(>)', '(<)', '(=)']:
            provenance = node_get_provenance(node, key)
            raise LoadError(LoadErrorReason.TRAILING_LIST_DIRECTIVE,
                            "{}: Attempt to override non-existing list".format(provenance))

        if isinstance(value, collections.Mapping):
            node_final_assertions(value)
        elif isinstance(value, list):
            list_final_assertions(value)


def list_final_assertions(values):
    for value in values:
        if isinstance(value, collections.Mapping):
            node_final_assertions(value)
        elif isinstance(value, list):
            list_final_assertions(value)


# assert_symbol_name()
#
# A helper function to check if a loaded string is a valid symbol
# name and to raise a consistent LoadError if not. For strings which
# are required to be symbols.
#
# Args:
#    provenance (Provenance): The provenance of the loaded symbol, or None
#    symbol_name (str): The loaded symbol name
#    purpose (str): The purpose of the string, for an error message
#    allow_dashes (bool): Whether dashes are allowed for this symbol
#
# Raises:
#    LoadError: If the symbol_name is invalid
#
# Note that dashes are generally preferred for variable names and
# usage in YAML, but things such as option names which will be
# evaluated with jinja2 cannot use dashes.
#
def assert_symbol_name(provenance, symbol_name, purpose, *, allow_dashes=True):
    valid_chars = string.digits + string.ascii_letters + '_'
    if allow_dashes:
        valid_chars += '-'

    valid = True
    if not symbol_name:
        valid = False
    elif any(x not in valid_chars for x in symbol_name):
        valid = False
    elif symbol_name[0] in string.digits:
        valid = False

    if not valid:
        detail = "Symbol names must contain only alphanumeric characters, " + \
                 "may not start with a digit, and may contain underscores"
        if allow_dashes:
            detail += " or dashes"

        message = "Invalid symbol name for {}: '{}'".format(purpose, symbol_name)
        if provenance is not None:
            message = "{}: {}".format(provenance, message)

        raise LoadError(LoadErrorReason.INVALID_SYMBOL_NAME,
                        message, detail=detail)
