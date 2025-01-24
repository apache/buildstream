# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: build/bazel/remote/asset/v1/remote_asset.proto
# Protobuf Python Version: 5.28.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    28,
    1,
    '',
    'build/bazel/remote/asset/v1/remote_asset.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2 as build_dot_bazel_dot_remote_dot_execution_dot_v2_dot_remote__execution__pb2
from buildstream._protos.google.api import annotations_pb2 as google_dot_api_dot_annotations__pb2
from google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2
from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
from buildstream._protos.google.rpc import status_pb2 as google_dot_rpc_dot_status__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n.build/bazel/remote/asset/v1/remote_asset.proto\x12\x1b\x62uild.bazel.remote.asset.v1\x1a\x36\x62uild/bazel/remote/execution/v2/remote_execution.proto\x1a\x1cgoogle/api/annotations.proto\x1a\x1egoogle/protobuf/duration.proto\x1a\x1fgoogle/protobuf/timestamp.proto\x1a\x17google/rpc/status.proto\"(\n\tQualifier\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\"\xac\x02\n\x10\x46\x65tchBlobRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12*\n\x07timeout\x18\x02 \x01(\x0b\x32\x19.google.protobuf.Duration\x12;\n\x17oldest_content_accepted\x18\x03 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x0c\n\x04uris\x18\x04 \x03(\t\x12:\n\nqualifiers\x18\x05 \x03(\x0b\x32&.build.bazel.remote.asset.v1.Qualifier\x12N\n\x0f\x64igest_function\x18\x06 \x01(\x0e\x32\x35.build.bazel.remote.execution.v2.DigestFunction.Value\"\xbe\x02\n\x11\x46\x65tchBlobResponse\x12\"\n\x06status\x18\x01 \x01(\x0b\x32\x12.google.rpc.Status\x12\x0b\n\x03uri\x18\x02 \x01(\t\x12:\n\nqualifiers\x18\x03 \x03(\x0b\x32&.build.bazel.remote.asset.v1.Qualifier\x12.\n\nexpires_at\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12<\n\x0b\x62lob_digest\x18\x05 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12N\n\x0f\x64igest_function\x18\x06 \x01(\x0e\x32\x35.build.bazel.remote.execution.v2.DigestFunction.Value\"\xb1\x02\n\x15\x46\x65tchDirectoryRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12*\n\x07timeout\x18\x02 \x01(\x0b\x32\x19.google.protobuf.Duration\x12;\n\x17oldest_content_accepted\x18\x03 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x0c\n\x04uris\x18\x04 \x03(\t\x12:\n\nqualifiers\x18\x05 \x03(\x0b\x32&.build.bazel.remote.asset.v1.Qualifier\x12N\n\x0f\x64igest_function\x18\x06 \x01(\x0e\x32\x35.build.bazel.remote.execution.v2.DigestFunction.Value\"\xcd\x02\n\x16\x46\x65tchDirectoryResponse\x12\"\n\x06status\x18\x01 \x01(\x0b\x32\x12.google.rpc.Status\x12\x0b\n\x03uri\x18\x02 \x01(\t\x12:\n\nqualifiers\x18\x03 \x03(\x0b\x32&.build.bazel.remote.asset.v1.Qualifier\x12.\n\nexpires_at\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x46\n\x15root_directory_digest\x18\x05 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12N\n\x0f\x64igest_function\x18\x06 \x01(\x0e\x32\x35.build.bazel.remote.execution.v2.DigestFunction.Value\"\xbb\x03\n\x0fPushBlobRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04uris\x18\x02 \x03(\t\x12:\n\nqualifiers\x18\x03 \x03(\x0b\x32&.build.bazel.remote.asset.v1.Qualifier\x12-\n\texpire_at\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12<\n\x0b\x62lob_digest\x18\x05 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x41\n\x10references_blobs\x18\x06 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12G\n\x16references_directories\x18\x07 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12N\n\x0f\x64igest_function\x18\x08 \x01(\x0e\x32\x35.build.bazel.remote.execution.v2.DigestFunction.Value\"\x12\n\x10PushBlobResponse\"\xca\x03\n\x14PushDirectoryRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04uris\x18\x02 \x03(\t\x12:\n\nqualifiers\x18\x03 \x03(\x0b\x32&.build.bazel.remote.asset.v1.Qualifier\x12-\n\texpire_at\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x46\n\x15root_directory_digest\x18\x05 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x41\n\x10references_blobs\x18\x06 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12G\n\x16references_directories\x18\x07 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12N\n\x0f\x64igest_function\x18\x08 \x01(\x0e\x32\x35.build.bazel.remote.execution.v2.DigestFunction.Value\"\x17\n\x15PushDirectoryResponse2\xdd\x02\n\x05\x46\x65tch\x12\x9e\x01\n\tFetchBlob\x12-.build.bazel.remote.asset.v1.FetchBlobRequest\x1a..build.bazel.remote.asset.v1.FetchBlobResponse\"2\x82\xd3\xe4\x93\x02,\"\'/v1/{instance_name=**}/assets:fetchBlob:\x01*\x12\xb2\x01\n\x0e\x46\x65tchDirectory\x12\x32.build.bazel.remote.asset.v1.FetchDirectoryRequest\x1a\x33.build.bazel.remote.asset.v1.FetchDirectoryResponse\"7\x82\xd3\xe4\x93\x02\x31\",/v1/{instance_name=**}/assets:fetchDirectory:\x01*2\xd4\x02\n\x04Push\x12\x9a\x01\n\x08PushBlob\x12,.build.bazel.remote.asset.v1.PushBlobRequest\x1a-.build.bazel.remote.asset.v1.PushBlobResponse\"1\x82\xd3\xe4\x93\x02+\"&/v1/{instance_name=**}/assets:pushBlob:\x01*\x12\xae\x01\n\rPushDirectory\x12\x31.build.bazel.remote.asset.v1.PushDirectoryRequest\x1a\x32.build.bazel.remote.asset.v1.PushDirectoryResponse\"6\x82\xd3\xe4\x93\x02\x30\"+/v1/{instance_name=**}/assets:pushDirectory:\x01*B\x9f\x01\n\x1b\x62uild.bazel.remote.asset.v1B\x10RemoteAssetProtoP\x01ZIgithub.com/bazelbuild/remote-apis/build/bazel/remote/asset/v1;remoteasset\xa2\x02\x02RA\xaa\x02\x1b\x42uild.Bazel.Remote.Asset.v1b\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'build.bazel.remote.asset.v1.remote_asset_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  _globals['DESCRIPTOR']._loaded_options = None
  _globals['DESCRIPTOR']._serialized_options = b'\n\033build.bazel.remote.asset.v1B\020RemoteAssetProtoP\001ZIgithub.com/bazelbuild/remote-apis/build/bazel/remote/asset/v1;remoteasset\242\002\002RA\252\002\033Build.Bazel.Remote.Asset.v1'
  _globals['_FETCH'].methods_by_name['FetchBlob']._loaded_options = None
  _globals['_FETCH'].methods_by_name['FetchBlob']._serialized_options = b'\202\323\344\223\002,\"\'/v1/{instance_name=**}/assets:fetchBlob:\001*'
  _globals['_FETCH'].methods_by_name['FetchDirectory']._loaded_options = None
  _globals['_FETCH'].methods_by_name['FetchDirectory']._serialized_options = b'\202\323\344\223\0021\",/v1/{instance_name=**}/assets:fetchDirectory:\001*'
  _globals['_PUSH'].methods_by_name['PushBlob']._loaded_options = None
  _globals['_PUSH'].methods_by_name['PushBlob']._serialized_options = b'\202\323\344\223\002+\"&/v1/{instance_name=**}/assets:pushBlob:\001*'
  _globals['_PUSH'].methods_by_name['PushDirectory']._loaded_options = None
  _globals['_PUSH'].methods_by_name['PushDirectory']._serialized_options = b'\202\323\344\223\0020\"+/v1/{instance_name=**}/assets:pushDirectory:\001*'
  _globals['_QUALIFIER']._serialized_start=255
  _globals['_QUALIFIER']._serialized_end=295
  _globals['_FETCHBLOBREQUEST']._serialized_start=298
  _globals['_FETCHBLOBREQUEST']._serialized_end=598
  _globals['_FETCHBLOBRESPONSE']._serialized_start=601
  _globals['_FETCHBLOBRESPONSE']._serialized_end=919
  _globals['_FETCHDIRECTORYREQUEST']._serialized_start=922
  _globals['_FETCHDIRECTORYREQUEST']._serialized_end=1227
  _globals['_FETCHDIRECTORYRESPONSE']._serialized_start=1230
  _globals['_FETCHDIRECTORYRESPONSE']._serialized_end=1563
  _globals['_PUSHBLOBREQUEST']._serialized_start=1566
  _globals['_PUSHBLOBREQUEST']._serialized_end=2009
  _globals['_PUSHBLOBRESPONSE']._serialized_start=2011
  _globals['_PUSHBLOBRESPONSE']._serialized_end=2029
  _globals['_PUSHDIRECTORYREQUEST']._serialized_start=2032
  _globals['_PUSHDIRECTORYREQUEST']._serialized_end=2490
  _globals['_PUSHDIRECTORYRESPONSE']._serialized_start=2492
  _globals['_PUSHDIRECTORYRESPONSE']._serialized_end=2515
  _globals['_FETCH']._serialized_start=2518
  _globals['_FETCH']._serialized_end=2867
  _globals['_PUSH']._serialized_start=2870
  _globals['_PUSH']._serialized_end=3210
# @@protoc_insertion_point(module_scope)
