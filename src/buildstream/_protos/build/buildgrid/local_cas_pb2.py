# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: build/buildgrid/local_cas.proto
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
    'build/buildgrid/local_cas.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2 as build_dot_bazel_dot_remote_dot_execution_dot_v2_dot_remote__execution__pb2
from buildstream._protos.google.rpc import status_pb2 as google_dot_rpc_dot_status__pb2
from google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1f\x62uild/buildgrid/local_cas.proto\x12\x0f\x62uild.buildgrid\x1a\x36\x62uild/bazel/remote/execution/v2/remote_execution.proto\x1a\x17google/rpc/status.proto\x1a\x1egoogle/protobuf/duration.proto\"p\n\x18\x46\x65tchMissingBlobsRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12=\n\x0c\x62lob_digests\x18\x02 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\xcc\x01\n\x19\x46\x65tchMissingBlobsResponse\x12\x46\n\tresponses\x18\x01 \x03(\x0b\x32\x33.build.buildgrid.FetchMissingBlobsResponse.Response\x1ag\n\x08Response\x12\x37\n\x06\x64igest\x18\x01 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x02 \x01(\x0b\x32\x12.google.rpc.Status\"q\n\x19UploadMissingBlobsRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12=\n\x0c\x62lob_digests\x18\x02 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\xce\x01\n\x1aUploadMissingBlobsResponse\x12G\n\tresponses\x18\x01 \x03(\x0b\x32\x34.build.buildgrid.UploadMissingBlobsResponse.Response\x1ag\n\x08Response\x12\x37\n\x06\x64igest\x18\x01 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x02 \x01(\x0b\x32\x12.google.rpc.Status\"\x81\x01\n\x10\x46\x65tchTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12<\n\x0broot_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x18\n\x10\x66\x65tch_file_blobs\x18\x03 \x01(\x08\"\x13\n\x11\x46\x65tchTreeResponse\"h\n\x11UploadTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12<\n\x0broot_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\x14\n\x12UploadTreeResponse\"\xe9\x01\n\x10StageTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12<\n\x0broot_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x0c\n\x04path\x18\x03 \x01(\t\x12I\n\x12\x61\x63\x63\x65ss_credentials\x18\x04 \x01(\x0b\x32-.build.buildgrid.StageTreeRequest.Credentials\x1a\'\n\x0b\x43redentials\x12\x0b\n\x03uid\x18\x01 \x01(\x03\x12\x0b\n\x03gid\x18\x02 \x01(\x03\"!\n\x11StageTreeResponse\x12\x0c\n\x04path\x18\x01 \x01(\t\"\x86\x02\n\x12\x43\x61ptureTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04root\x18\x06 \x01(\t\x12\x0c\n\x04path\x18\x02 \x03(\t\x12\x1a\n\x12\x62ypass_local_cache\x18\x03 \x01(\x08\x12\x17\n\x0fnode_properties\x18\x04 \x03(\t\x12\x12\n\nmove_files\x18\x05 \x01(\x08\x12_\n\x17output_directory_format\x18\x07 \x01(\x0e\x32>.build.bazel.remote.execution.v2.Command.OutputDirectoryFormat\x12\x13\n\x0bskip_upload\x18\x08 \x01(\x08\"\x9c\x02\n\x13\x43\x61ptureTreeResponse\x12@\n\tresponses\x18\x01 \x03(\x0b\x32-.build.buildgrid.CaptureTreeResponse.Response\x1a\xc2\x01\n\x08Response\x12\x0c\n\x04path\x18\x01 \x01(\t\x12<\n\x0btree_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x03 \x01(\x0b\x32\x12.google.rpc.Status\x12\x46\n\x15root_directory_digest\x18\x04 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\xa6\x01\n\x13\x43\x61ptureFilesRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04root\x18\x06 \x01(\t\x12\x0c\n\x04path\x18\x02 \x03(\t\x12\x1a\n\x12\x62ypass_local_cache\x18\x03 \x01(\x08\x12\x17\n\x0fnode_properties\x18\x04 \x03(\t\x12\x12\n\nmove_files\x18\x05 \x01(\x08\x12\x13\n\x0bskip_upload\x18\x07 \x01(\x08\"\xb8\x02\n\x14\x43\x61ptureFilesResponse\x12\x41\n\tresponses\x18\x01 \x03(\x0b\x32..build.buildgrid.CaptureFilesResponse.Response\x1a\xdc\x01\n\x08Response\x12\x0c\n\x04path\x18\x01 \x01(\t\x12\x37\n\x06\x64igest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x03 \x01(\x0b\x32\x12.google.rpc.Status\x12\x15\n\ris_executable\x18\x04 \x01(\x08\x12H\n\x0fnode_properties\x18\x06 \x01(\x0b\x32/.build.bazel.remote.execution.v2.NodePropertiesJ\x04\x08\x05\x10\x06\"\x83\x01\n\x1fGetInstanceNameForRemoteRequest\x12\x0b\n\x03url\x18\x01 \x01(\t\x12\x15\n\rinstance_name\x18\x02 \x01(\t\x12\x13\n\x0bserver_cert\x18\x03 \x01(\x0c\x12\x12\n\nclient_key\x18\x04 \x01(\x0c\x12\x13\n\x0b\x63lient_cert\x18\x05 \x01(\x0c\"9\n GetInstanceNameForRemoteResponse\x12\x15\n\rinstance_name\x18\x01 \x01(\t\"\xf2\x02\n\x06Remote\x12\x0b\n\x03url\x18\x01 \x01(\t\x12\x15\n\rinstance_name\x18\x02 \x01(\t\x12\x13\n\x0bserver_cert\x18\x03 \x01(\x0c\x12\x12\n\nclient_key\x18\x04 \x01(\x0c\x12\x13\n\x0b\x63lient_cert\x18\x05 \x01(\x0c\x12\x19\n\x11\x61\x63\x63\x65ss_token_path\x18\x07 \x01(\t\x12?\n\x1c\x61\x63\x63\x65ss_token_reload_interval\x18\x08 \x01(\x0b\x32\x19.google.protobuf.Duration\x12\x31\n\x0ekeepalive_time\x18\x06 \x01(\x0b\x32\x19.google.protobuf.Duration\x12\x13\n\x0bretry_limit\x18\t \x01(\x03\x12.\n\x0bretry_delay\x18\n \x01(\x0b\x32\x19.google.protobuf.Duration\x12\x32\n\x0frequest_timeout\x18\x0b \x01(\x0b\x32\x19.google.protobuf.Duration\"\x81\x02\n GetInstanceNameForRemotesRequest\x12\x15\n\rinstance_name\x18\x03 \x01(\t\x12<\n\x1b\x63ontent_addressable_storage\x18\x01 \x01(\x0b\x32\x17.build.buildgrid.Remote\x12-\n\x0cremote_asset\x18\x02 \x01(\x0b\x32\x17.build.buildgrid.Remote\x12-\n\x0c\x61\x63tion_cache\x18\x04 \x01(\x0b\x32\x17.build.buildgrid.Remote\x12*\n\texecution\x18\x05 \x01(\x0b\x32\x17.build.buildgrid.Remote\":\n!GetInstanceNameForRemotesResponse\x12\x15\n\rinstance_name\x18\x01 \x01(\t\"I\n\"GetInstanceNameForNamespaceRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04root\x18\x02 \x01(\t\"<\n#GetInstanceNameForNamespaceResponse\x12\x15\n\rinstance_name\x18\x01 \x01(\t\"\x1a\n\x18GetLocalDiskUsageRequest\"D\n\x19GetLocalDiskUsageResponse\x12\x12\n\nsize_bytes\x18\x01 \x01(\x03\x12\x13\n\x0bquota_bytes\x18\x02 \x01(\x03\x32\xc9\t\n\x1eLocalContentAddressableStorage\x12l\n\x11\x46\x65tchMissingBlobs\x12).build.buildgrid.FetchMissingBlobsRequest\x1a*.build.buildgrid.FetchMissingBlobsResponse\"\x00\x12o\n\x12UploadMissingBlobs\x12*.build.buildgrid.UploadMissingBlobsRequest\x1a+.build.buildgrid.UploadMissingBlobsResponse\"\x00\x12T\n\tFetchTree\x12!.build.buildgrid.FetchTreeRequest\x1a\".build.buildgrid.FetchTreeResponse\"\x00\x12W\n\nUploadTree\x12\".build.buildgrid.UploadTreeRequest\x1a#.build.buildgrid.UploadTreeResponse\"\x00\x12X\n\tStageTree\x12!.build.buildgrid.StageTreeRequest\x1a\".build.buildgrid.StageTreeResponse\"\x00(\x01\x30\x01\x12Z\n\x0b\x43\x61ptureTree\x12#.build.buildgrid.CaptureTreeRequest\x1a$.build.buildgrid.CaptureTreeResponse\"\x00\x12]\n\x0c\x43\x61ptureFiles\x12$.build.buildgrid.CaptureFilesRequest\x1a%.build.buildgrid.CaptureFilesResponse\"\x00\x12\x81\x01\n\x18GetInstanceNameForRemote\x12\x30.build.buildgrid.GetInstanceNameForRemoteRequest\x1a\x31.build.buildgrid.GetInstanceNameForRemoteResponse\"\x00\x12\x84\x01\n\x19GetInstanceNameForRemotes\x12\x31.build.buildgrid.GetInstanceNameForRemotesRequest\x1a\x32.build.buildgrid.GetInstanceNameForRemotesResponse\"\x00\x12\x8a\x01\n\x1bGetInstanceNameForNamespace\x12\x33.build.buildgrid.GetInstanceNameForNamespaceRequest\x1a\x34.build.buildgrid.GetInstanceNameForNamespaceResponse\"\x00\x12l\n\x11GetLocalDiskUsage\x12).build.buildgrid.GetLocalDiskUsageRequest\x1a*.build.buildgrid.GetLocalDiskUsageResponse\"\x00\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'build.buildgrid.local_cas_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_FETCHMISSINGBLOBSREQUEST']._serialized_start=165
  _globals['_FETCHMISSINGBLOBSREQUEST']._serialized_end=277
  _globals['_FETCHMISSINGBLOBSRESPONSE']._serialized_start=280
  _globals['_FETCHMISSINGBLOBSRESPONSE']._serialized_end=484
  _globals['_FETCHMISSINGBLOBSRESPONSE_RESPONSE']._serialized_start=381
  _globals['_FETCHMISSINGBLOBSRESPONSE_RESPONSE']._serialized_end=484
  _globals['_UPLOADMISSINGBLOBSREQUEST']._serialized_start=486
  _globals['_UPLOADMISSINGBLOBSREQUEST']._serialized_end=599
  _globals['_UPLOADMISSINGBLOBSRESPONSE']._serialized_start=602
  _globals['_UPLOADMISSINGBLOBSRESPONSE']._serialized_end=808
  _globals['_UPLOADMISSINGBLOBSRESPONSE_RESPONSE']._serialized_start=381
  _globals['_UPLOADMISSINGBLOBSRESPONSE_RESPONSE']._serialized_end=484
  _globals['_FETCHTREEREQUEST']._serialized_start=811
  _globals['_FETCHTREEREQUEST']._serialized_end=940
  _globals['_FETCHTREERESPONSE']._serialized_start=942
  _globals['_FETCHTREERESPONSE']._serialized_end=961
  _globals['_UPLOADTREEREQUEST']._serialized_start=963
  _globals['_UPLOADTREEREQUEST']._serialized_end=1067
  _globals['_UPLOADTREERESPONSE']._serialized_start=1069
  _globals['_UPLOADTREERESPONSE']._serialized_end=1089
  _globals['_STAGETREEREQUEST']._serialized_start=1092
  _globals['_STAGETREEREQUEST']._serialized_end=1325
  _globals['_STAGETREEREQUEST_CREDENTIALS']._serialized_start=1286
  _globals['_STAGETREEREQUEST_CREDENTIALS']._serialized_end=1325
  _globals['_STAGETREERESPONSE']._serialized_start=1327
  _globals['_STAGETREERESPONSE']._serialized_end=1360
  _globals['_CAPTURETREEREQUEST']._serialized_start=1363
  _globals['_CAPTURETREEREQUEST']._serialized_end=1625
  _globals['_CAPTURETREERESPONSE']._serialized_start=1628
  _globals['_CAPTURETREERESPONSE']._serialized_end=1912
  _globals['_CAPTURETREERESPONSE_RESPONSE']._serialized_start=1718
  _globals['_CAPTURETREERESPONSE_RESPONSE']._serialized_end=1912
  _globals['_CAPTUREFILESREQUEST']._serialized_start=1915
  _globals['_CAPTUREFILESREQUEST']._serialized_end=2081
  _globals['_CAPTUREFILESRESPONSE']._serialized_start=2084
  _globals['_CAPTUREFILESRESPONSE']._serialized_end=2396
  _globals['_CAPTUREFILESRESPONSE_RESPONSE']._serialized_start=2176
  _globals['_CAPTUREFILESRESPONSE_RESPONSE']._serialized_end=2396
  _globals['_GETINSTANCENAMEFORREMOTEREQUEST']._serialized_start=2399
  _globals['_GETINSTANCENAMEFORREMOTEREQUEST']._serialized_end=2530
  _globals['_GETINSTANCENAMEFORREMOTERESPONSE']._serialized_start=2532
  _globals['_GETINSTANCENAMEFORREMOTERESPONSE']._serialized_end=2589
  _globals['_REMOTE']._serialized_start=2592
  _globals['_REMOTE']._serialized_end=2962
  _globals['_GETINSTANCENAMEFORREMOTESREQUEST']._serialized_start=2965
  _globals['_GETINSTANCENAMEFORREMOTESREQUEST']._serialized_end=3222
  _globals['_GETINSTANCENAMEFORREMOTESRESPONSE']._serialized_start=3224
  _globals['_GETINSTANCENAMEFORREMOTESRESPONSE']._serialized_end=3282
  _globals['_GETINSTANCENAMEFORNAMESPACEREQUEST']._serialized_start=3284
  _globals['_GETINSTANCENAMEFORNAMESPACEREQUEST']._serialized_end=3357
  _globals['_GETINSTANCENAMEFORNAMESPACERESPONSE']._serialized_start=3359
  _globals['_GETINSTANCENAMEFORNAMESPACERESPONSE']._serialized_end=3419
  _globals['_GETLOCALDISKUSAGEREQUEST']._serialized_start=3421
  _globals['_GETLOCALDISKUSAGEREQUEST']._serialized_end=3447
  _globals['_GETLOCALDISKUSAGERESPONSE']._serialized_start=3449
  _globals['_GETLOCALDISKUSAGERESPONSE']._serialized_end=3517
  _globals['_LOCALCONTENTADDRESSABLESTORAGE']._serialized_start=3520
  _globals['_LOCALCONTENTADDRESSABLESTORAGE']._serialized_end=4745
# @@protoc_insertion_point(module_scope)
