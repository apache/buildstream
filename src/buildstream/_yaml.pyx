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
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Daniel Silverstone <daniel.silverstone@codethink.co.uk>
#        James Ennis <james.ennis@codethink.co.uk>
#        Benjamin Schubert <bschubert@bloomberg.net>

import datetime
import sys
from io import StringIO
from contextlib import ExitStack
from collections import OrderedDict
from collections.abc import Mapping

from ruamel import yaml

from ._exceptions import LoadError
from .exceptions import LoadErrorReason
from . cimport node
from .node cimport MappingNode, ScalarNode, SequenceNode


# These exceptions are intended to be caught entirely within
# the BuildStream framework, hence they do not reside in the
# public exceptions.py

class YAMLLoadError(Exception):
    pass


# Represents the various states in which the Representer can be
# while parsing yaml.
cdef enum RepresenterState:
    doc
    init
    stream
    wait_key
    wait_list_item
    wait_value


ctypedef RepresenterState (*representer_action)(Representer, object)

# Representer for YAML events comprising input to the BuildStream format.
#
# All streams MUST represent a single document which must be a Mapping.
# Anything else is considered an error.
#
# Mappings must only have string keys, values are always represented as
# strings if they are scalar, or else as simple dictionaries and lists.
#
cdef class Representer:

    cdef int _file_index
    cdef RepresenterState state
    cdef list output, keys

    # Initialise a new representer
    #
    # The file index is used to store into the Node instances so that the
    # provenance of the YAML can be tracked.
    #
    # Args:
    #   file_index (int): The index of this YAML file
    def __init__(self, int file_index):
        self._file_index = file_index
        self.state = RepresenterState.init
        self.output = []
        self.keys = []

    # Handle a YAML parse event
    #
    # Args:
    #   event (YAML Event): The event to be handled
    #
    # Raises:
    #   YAMLLoadError: Something went wrong.
    cdef void handle_event(self, event) except *:
        if getattr(event, "anchor", None) is not None:
            raise YAMLLoadError("Anchors are disallowed in BuildStream at line {} column {}"
                                .format(event.start_mark.line, event.start_mark.column))

        cdef str event_name = event.__class__.__name__

        if event_name == "ScalarEvent":
            if event.tag is not None:
                if not event.tag.startswith("tag:yaml.org,2002:"):
                    raise YAMLLoadError(
                        "Non-core tag expressed in input.  " +
                        "This is disallowed in BuildStream. At line {} column {}"
                        .format(event.start_mark.line, event.start_mark.column))

        cdef representer_action handler = self._get_handler_for_event(event_name)
        if not handler:
            raise YAMLLoadError(
                "Invalid input detected. No handler for {} in state {} at line {} column {}"
                .format(event, self.state, event.start_mark.line, event.start_mark.column))

        # Cython weirdness here, we need to pass self to the function
        self.state = <RepresenterState> handler(self, event)  # pylint: disable=not-callable

    # Get the output of the YAML parse
    #
    # Returns:
    #   (Node or None): Return the Node instance of the top level mapping or
    #                   None if there wasn't one.
    cdef MappingNode get_output(self):
        if len(self.output):
            return self.output[0]
        return None

    cdef representer_action _get_handler_for_event(self, str event_name):
        if self.state == RepresenterState.wait_list_item:
            if event_name == "ScalarEvent":
                return self._handle_wait_list_item_ScalarEvent
            elif event_name == "MappingStartEvent":
                return self._handle_wait_list_item_MappingStartEvent
            elif event_name == "SequenceStartEvent":
                return self._handle_wait_list_item_SequenceStartEvent
            elif event_name == "SequenceEndEvent":
                return self._handle_wait_list_item_SequenceEndEvent
        elif self.state == RepresenterState.wait_value:
            if event_name == "ScalarEvent":
                return self._handle_wait_value_ScalarEvent
            elif event_name == "MappingStartEvent":
                return self._handle_wait_value_MappingStartEvent
            elif event_name == "SequenceStartEvent":
                return self._handle_wait_value_SequenceStartEvent
        elif self.state == RepresenterState.wait_key:
            if event_name == "ScalarEvent":
                return self._handle_wait_key_ScalarEvent
            elif event_name == "MappingEndEvent":
                return self._handle_wait_key_MappingEndEvent
        elif self.state == RepresenterState.stream:
            if event_name == "DocumentStartEvent":
                return self._handle_stream_DocumentStartEvent
            elif event_name == "StreamEndEvent":
                return self._handle_stream_StreamEndEvent
        elif self.state == RepresenterState.doc:
            if event_name == "MappingStartEvent":
                return self._handle_doc_MappingStartEvent
            elif event_name == "DocumentEndEvent":
                return self._handle_doc_DocumentEndEvent
        elif self.state == RepresenterState.init and event_name == "StreamStartEvent":
            return self._handle_init_StreamStartEvent
        return NULL

    cdef RepresenterState _handle_init_StreamStartEvent(self, object ev):
        return RepresenterState.stream

    cdef RepresenterState _handle_stream_DocumentStartEvent(self, object ev):
        return RepresenterState.doc

    cdef RepresenterState _handle_doc_MappingStartEvent(self, object ev):
        newmap = MappingNode.__new__(MappingNode, self._file_index, ev.start_mark.line, ev.start_mark.column, {})
        self.output.append(newmap)
        return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_key_ScalarEvent(self, object ev):
        self.keys.append(ev.value)
        return RepresenterState.wait_value

    cdef RepresenterState _handle_wait_value_ScalarEvent(self, object ev):
        key = self.keys.pop()
        (<MappingNode> self.output[-1]).value[key] = \
            ScalarNode.__new__(ScalarNode, self._file_index, ev.start_mark.line, ev.start_mark.column, ev.value)
        return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_value_MappingStartEvent(self, object ev):
        cdef RepresenterState new_state = self._handle_doc_MappingStartEvent(ev)
        key = self.keys.pop()
        (<MappingNode> self.output[-2]).value[key] = self.output[-1]
        return new_state

    cdef RepresenterState _handle_wait_key_MappingEndEvent(self, object ev):
        # We've finished a mapping, so pop it off the output stack
        # unless it's the last one in which case we leave it
        if len(self.output) > 1:
            self.output.pop()
            if type(self.output[-1]) is SequenceNode:
                return RepresenterState.wait_list_item
            else:
                return RepresenterState.wait_key
        else:
            return RepresenterState.doc

    cdef RepresenterState _handle_wait_value_SequenceStartEvent(self, object ev):
        self.output.append(SequenceNode.__new__(
            SequenceNode, self._file_index, ev.start_mark.line, ev.start_mark.column, []))
        (<MappingNode> self.output[-2]).value[self.keys[-1]] = self.output[-1]
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_SequenceStartEvent(self, object ev):
        self.keys.append(len((<SequenceNode> self.output[-1]).value))
        self.output.append(SequenceNode.__new__(
            SequenceNode, self._file_index, ev.start_mark.line, ev.start_mark.column, []))
        (<SequenceNode> self.output[-2]).value.append(self.output[-1])
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_SequenceEndEvent(self, object ev):
        # When ending a sequence, we need to pop a key because we retain the
        # key until the end so that if we need to mutate the underlying entry
        # we can.
        key = self.keys.pop()
        self.output.pop()
        if type(key) is int:
            return RepresenterState.wait_list_item
        else:
            return RepresenterState.wait_key

    cdef RepresenterState _handle_wait_list_item_ScalarEvent(self, object ev):
        (<SequenceNode> self.output[-1]).value.append(
           ScalarNode.__new__(ScalarNode, self._file_index, ev.start_mark.line, ev.start_mark.column, ev.value))
        return RepresenterState.wait_list_item

    cdef RepresenterState _handle_wait_list_item_MappingStartEvent(self, object ev):
        cdef RepresenterState new_state = self._handle_doc_MappingStartEvent(ev)
        (<SequenceNode> self.output[-2]).value.append(self.output[-1])
        return new_state

    cdef RepresenterState _handle_doc_DocumentEndEvent(self, object ev):
        if len(self.output) != 1:
            raise YAMLLoadError("Zero, or more than one document found in YAML stream")
        return RepresenterState.stream

    cdef RepresenterState _handle_stream_StreamEndEvent(self, object ev):
        return RepresenterState.init


# Loads a dictionary from some YAML
#
# Args:
#    filename (str): The YAML file to load
#    shortname (str): The filename in shorthand for error reporting (or None)
#    copy_tree (bool): Whether to make a copy, preserving the original toplevels
#                      for later serialization
#    project (Project): The (optional) project to associate the parsed YAML with
#
# Returns (dict): A loaded copy of the YAML file with provenance information
#
# Raises: LoadError
#
cpdef MappingNode load(str filename, str shortname, bint copy_tree=False, object project=None):
    cdef MappingNode data

    if not shortname:
        shortname = filename

    cdef str displayname
    if (project is not None) and (project.junction is not None):
        displayname = "{}:{}".format(project.junction.name, shortname)
    else:
        displayname = shortname

    cdef Py_ssize_t file_number = node._create_new_file(filename, shortname, displayname, project)

    try:
        with open(filename) as f:
            contents = f.read()

        data = load_data(contents,
                         file_index=file_number,
                         file_name=filename,
                         copy_tree=copy_tree)

        return data
    except FileNotFoundError as e:
        raise LoadError("Could not find file at {}".format(filename),
                        LoadErrorReason.MISSING_FILE) from e
    except IsADirectoryError as e:
        raise LoadError("{} is a directory".format(filename),
                        LoadErrorReason.LOADING_DIRECTORY) from e
    except LoadError as e:
        raise LoadError("{}: {}".format(displayname, e), e.reason) from e


# Like load(), but doesnt require the data to be in a file
#
cpdef MappingNode load_data(str data, int file_index=node._SYNTHETIC_FILE_INDEX, str file_name=None, bint copy_tree=False):
    cdef Representer rep

    try:
        rep = Representer(file_index)
        parser = yaml.CParser(data)

        try:
            while parser.check_event():
                rep.handle_event(parser.get_event())
        finally:
            parser.dispose()

        contents = rep.get_output()
    except YAMLLoadError as e:
        raise LoadError("Malformed YAML:\n\n{}\n\n".format(e),
                        LoadErrorReason.INVALID_YAML) from e
    except Exception as e:
        raise LoadError("Severely malformed YAML:\n\n{}\n\n".format(e),
                        LoadErrorReason.INVALID_YAML) from e

    if type(contents) != MappingNode:
        # Special case allowance for None, when the loaded file has only comments in it.
        if contents is None:
            contents = MappingNode.__new__(MappingNode, file_index, 0, 0, {})
        else:
            raise LoadError("YAML file has content of type '{}' instead of expected type 'dict': {}"
                            .format(type(contents[0]).__name__, file_name),
                            LoadErrorReason.INVALID_YAML)

    # Store this away because we'll use it later for "top level" provenance
    node._set_root_node_for_file(file_index, contents)

    if copy_tree:
        contents = contents.clone()
    return contents


###############################################################################

# Roundtrip code

# Represent Nodes automatically

def represent_mapping(self, MappingNode mapping):
    return self.represent_dict(mapping.value)

def represent_scalar(self, ScalarNode scalar):
    # We load None values as strings, and also save them as strings
    if scalar.value is None:
        return self.represent_str("")
    return self.represent_str(scalar.value)

def represent_sequence(self, SequenceNode sequence):
    return self.represent_list(sequence.value)


yaml.RoundTripRepresenter.add_representer(MappingNode, represent_mapping)
yaml.RoundTripRepresenter.add_representer(ScalarNode, represent_scalar)
yaml.RoundTripRepresenter.add_representer(SequenceNode, represent_sequence)

# Represent simple types as strings

def represent_as_str(self, value):
    return self.represent_str(str(value))

yaml.RoundTripRepresenter.add_representer(type(None), represent_as_str)
yaml.RoundTripRepresenter.add_representer(int, represent_as_str)
yaml.RoundTripRepresenter.add_representer(float, represent_as_str)
yaml.RoundTripRepresenter.add_representer(bool, represent_as_str)
yaml.RoundTripRepresenter.add_representer(datetime.datetime, represent_as_str)
yaml.RoundTripRepresenter.add_representer(datetime.date, represent_as_str)

# Always represent things consistently:

yaml.RoundTripRepresenter.add_representer(OrderedDict,
                                          yaml.SafeRepresenter.represent_dict)

# Always parse things consistently

yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:int',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:float',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:bool',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:null',
                                          yaml.RoundTripConstructor.construct_yaml_str)
yaml.RoundTripConstructor.add_constructor(u'tag:yaml.org,2002:timestamp',
                                          yaml.RoundTripConstructor.construct_yaml_str)

# This is a dumper used during roundtrip_dump which forces every scalar to be
# a plain string, in order to match the output format to the input format.
#
# If you discover something is broken, please add a test case to the roundtrip
# test in tests/internals/yaml/roundtrip-test.yaml
def prepare_roundtrip_yaml():
    yml = yaml.YAML()
    yml.preserve_quotes=True

    # For each of YAML 1.1 and 1.2, force everything to be a plain string

    for version in [(1, 1), (1, 2), None]:
        yml.resolver.add_version_implicit_resolver(
            version,
            u'tag:yaml.org,2002:str',
            yaml.util.RegExp(r'.*'),
            None)

    return yml


# roundtrip_load()
#
# Load a YAML file into memory in a form which allows roundtripping as best
# as ruamel permits.
#
# Note, the returned objects can be treated as Mappings and Lists and Strings
# but replacing content wholesale with plain dicts and lists may result
# in a loss of comments and formatting.
#
# Args:
#    filename (str): The file to load in
#    allow_missing (bool): Optionally set this to True to allow missing files
#
# Returns:
#    (Mapping): The loaded YAML mapping.
#
# Raises:
#    (LoadError): If the file is missing, or a directory, this is raised.
#                 Also if the YAML is malformed.
#
def roundtrip_load(filename, *, allow_missing=False):
    yml = prepare_roundtrip_yaml()
    try:
        with open(filename, "r") as fh:
            try:
                contents = yml.load(fh)
            except (yaml.scanner.ScannerError, yaml.composer.ComposerError, yaml.parser.ParserError) as e:
                raise LoadError("Malformed YAML:\n\n{}\n\n{}\n".format(e.problem, e.problem_mark),
                                LoadErrorReason.INVALID_YAML) from e

            # Special case empty files at this point
            if contents is None:
                # We'll make them empty mappings like the main Node loader
                contents = {}

            if not isinstance(contents, Mapping):
                raise LoadError("YAML file has content of type '{}' instead of expected type 'dict': {}"
                                .format(type(contents).__name__, filename), LoadErrorReason.INVALID_YAML)
    except FileNotFoundError as e:
        if allow_missing:
            # Missing files are always empty dictionaries
            return {}
        else:
            raise LoadError("Could not find file at {}".format(filename),
                            LoadErrorReason.MISSING_FILE) from e
    except IsADirectoryError as e:
        raise LoadError("{} is a directory.".format(filename),
                        LoadErrorReason.LOADING_DIRECTORY) from e
    return contents


# roundtrip_dump()
#
# Dumps the given contents as a YAML file.  Ideally the contents came from
# parsing with `roundtrip_load` or `roundtrip_load_data` so that they will be
# dumped in the same form as they came from.
#
# If `file` is a string, it is the filename to write to, if `file` has a
# `write` method, it's treated as a stream, otherwise output is to stdout.
#
# Args:
#    contents (Mapping or list): The content to write out as YAML.
#    file (any): The file to write to
#
def roundtrip_dump(contents, file=None):
    yml = prepare_roundtrip_yaml()
    with ExitStack() as stack:
        if type(file) is str:
            from . import utils
            f = stack.enter_context(utils.save_file_atomic(file, 'w'))
        elif hasattr(file, 'write'):
            f = file
        else:
            f = sys.stdout
        yml.dump(contents, f)


# roundtrip_dump_string()
#
# Helper to call roundtrip_dump() but get the content in a string.
#
# Args:
#    contents (Mapping or list): The content to write out as YAML.
#
# Returns:
#    (str): The generated string
#
def roundtrip_dump_string(node):
    with StringIO() as f:
        roundtrip_dump(node, f)
        return f.getvalue()
