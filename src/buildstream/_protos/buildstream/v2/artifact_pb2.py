# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: buildstream/v2/artifact.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'buildstream/v2/artifact.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2 as build_dot_bazel_dot_remote_dot_execution_dot_v2_dot_remote__execution__pb2
from buildstream._protos.google.api import annotations_pb2 as google_dot_api_dot_annotations__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1d\x62uildstream/v2/artifact.proto\x12\x0e\x62uildstream.v2\x1a\x36\x62uild/bazel/remote/execution/v2/remote_execution.proto\x1a\x1cgoogle/api/annotations.proto\"\x89\x07\n\x08\x41rtifact\x12\x0f\n\x07version\x18\x01 \x01(\x05\x12\x15\n\rbuild_success\x18\x02 \x01(\x08\x12\x13\n\x0b\x62uild_error\x18\x03 \x01(\t\x12\x1b\n\x13\x62uild_error_details\x18\x04 \x01(\t\x12\x12\n\nstrong_key\x18\x05 \x01(\t\x12\x10\n\x08weak_key\x18\x06 \x01(\t\x12\x16\n\x0ewas_workspaced\x18\x07 \x01(\x08\x12\x36\n\x05\x66iles\x18\x08 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x37\n\nbuild_deps\x18\t \x03(\x0b\x32#.buildstream.v2.Artifact.Dependency\x12<\n\x0bpublic_data\x18\n \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12.\n\x04logs\x18\x0b \x03(\x0b\x32 .buildstream.v2.Artifact.LogFile\x12:\n\tbuildtree\x18\x0c \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x38\n\x07sources\x18\r \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x43\n\x12low_diversity_meta\x18\x0e \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x44\n\x13high_diversity_meta\x18\x0f \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x12\n\nstrict_key\x18\x10 \x01(\t\x12:\n\tbuildroot\x18\x11 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x1a\x63\n\nDependency\x12\x14\n\x0cproject_name\x18\x01 \x01(\t\x12\x14\n\x0c\x65lement_name\x18\x02 \x01(\t\x12\x11\n\tcache_key\x18\x03 \x01(\t\x12\x16\n\x0ewas_workspaced\x18\x04 \x01(\x08\x1aP\n\x07LogFile\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x37\n\x06\x64igest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digestb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'buildstream.v2.artifact_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_ARTIFACT']._serialized_start=136
  _globals['_ARTIFACT']._serialized_end=1041
  _globals['_ARTIFACT_DEPENDENCY']._serialized_start=860
  _globals['_ARTIFACT_DEPENDENCY']._serialized_end=959
  _globals['_ARTIFACT_LOGFILE']._serialized_start=961
  _globals['_ARTIFACT_LOGFILE']._serialized_end=1041
# @@protoc_insertion_point(module_scope)
