# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: build/buildgrid/local_cas.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2 as build_dot_bazel_dot_remote_dot_execution_dot_v2_dot_remote__execution__pb2
from buildstream._protos.google.rpc import status_pb2 as google_dot_rpc_dot_status__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1f\x62uild/buildgrid/local_cas.proto\x12\x0f\x62uild.buildgrid\x1a\x36\x62uild/bazel/remote/execution/v2/remote_execution.proto\x1a\x17google/rpc/status.proto\"p\n\x18\x46\x65tchMissingBlobsRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12=\n\x0c\x62lob_digests\x18\x02 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\xcc\x01\n\x19\x46\x65tchMissingBlobsResponse\x12\x46\n\tresponses\x18\x01 \x03(\x0b\x32\x33.build.buildgrid.FetchMissingBlobsResponse.Response\x1ag\n\x08Response\x12\x37\n\x06\x64igest\x18\x01 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x02 \x01(\x0b\x32\x12.google.rpc.Status\"q\n\x19UploadMissingBlobsRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12=\n\x0c\x62lob_digests\x18\x02 \x03(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\xce\x01\n\x1aUploadMissingBlobsResponse\x12G\n\tresponses\x18\x01 \x03(\x0b\x32\x34.build.buildgrid.UploadMissingBlobsResponse.Response\x1ag\n\x08Response\x12\x37\n\x06\x64igest\x18\x01 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x02 \x01(\x0b\x32\x12.google.rpc.Status\"\x81\x01\n\x10\x46\x65tchTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12<\n\x0broot_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x18\n\x10\x66\x65tch_file_blobs\x18\x03 \x01(\x08\"\x13\n\x11\x46\x65tchTreeResponse\"h\n\x11UploadTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12<\n\x0broot_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\"\x14\n\x12UploadTreeResponse\"\xdc\x01\n\x10StageTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12<\n\x0broot_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\x0c\n\x04path\x18\x03 \x01(\t\x12I\n\x12\x61\x63\x63\x65ss_credentials\x18\x04 \x01(\x0b\x32-.build.buildgrid.StageTreeRequest.Credentials\x1a\x1a\n\x0b\x43redentials\x12\x0b\n\x03uid\x18\x01 \x01(\x03\"!\n\x11StageTreeResponse\x12\x0c\n\x04path\x18\x01 \x01(\t\"\x90\x01\n\x12\x43\x61ptureTreeRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04root\x18\x06 \x01(\t\x12\x0c\n\x04path\x18\x02 \x03(\t\x12\x1a\n\x12\x62ypass_local_cache\x18\x03 \x01(\x08\x12\x17\n\x0fnode_properties\x18\x04 \x03(\t\x12\x12\n\nmove_files\x18\x05 \x01(\x08\"\xd3\x01\n\x13\x43\x61ptureTreeResponse\x12@\n\tresponses\x18\x01 \x03(\x0b\x32-.build.buildgrid.CaptureTreeResponse.Response\x1az\n\x08Response\x12\x0c\n\x04path\x18\x01 \x01(\t\x12<\n\x0btree_digest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x03 \x01(\x0b\x32\x12.google.rpc.Status\"\x91\x01\n\x13\x43\x61ptureFilesRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04root\x18\x06 \x01(\t\x12\x0c\n\x04path\x18\x02 \x03(\t\x12\x1a\n\x12\x62ypass_local_cache\x18\x03 \x01(\x08\x12\x17\n\x0fnode_properties\x18\x04 \x03(\t\x12\x12\n\nmove_files\x18\x05 \x01(\x08\"\xb8\x02\n\x14\x43\x61ptureFilesResponse\x12\x41\n\tresponses\x18\x01 \x03(\x0b\x32..build.buildgrid.CaptureFilesResponse.Response\x1a\xdc\x01\n\x08Response\x12\x0c\n\x04path\x18\x01 \x01(\t\x12\x37\n\x06\x64igest\x18\x02 \x01(\x0b\x32\'.build.bazel.remote.execution.v2.Digest\x12\"\n\x06status\x18\x03 \x01(\x0b\x32\x12.google.rpc.Status\x12\x15\n\ris_executable\x18\x04 \x01(\x08\x12H\n\x0fnode_properties\x18\x06 \x01(\x0b\x32/.build.bazel.remote.execution.v2.NodePropertiesJ\x04\x08\x05\x10\x06\"\x83\x01\n\x1fGetInstanceNameForRemoteRequest\x12\x0b\n\x03url\x18\x01 \x01(\t\x12\x15\n\rinstance_name\x18\x02 \x01(\t\x12\x13\n\x0bserver_cert\x18\x03 \x01(\x0c\x12\x12\n\nclient_key\x18\x04 \x01(\x0c\x12\x13\n\x0b\x63lient_cert\x18\x05 \x01(\x0c\"9\n GetInstanceNameForRemoteResponse\x12\x15\n\rinstance_name\x18\x01 \x01(\t\"j\n\x06Remote\x12\x0b\n\x03url\x18\x01 \x01(\t\x12\x15\n\rinstance_name\x18\x02 \x01(\t\x12\x13\n\x0bserver_cert\x18\x03 \x01(\x0c\x12\x12\n\nclient_key\x18\x04 \x01(\x0c\x12\x13\n\x0b\x63lient_cert\x18\x05 \x01(\x0c\"\xd5\x01\n GetInstanceNameForRemotesRequest\x12\x15\n\rinstance_name\x18\x03 \x01(\t\x12<\n\x1b\x63ontent_addressable_storage\x18\x01 \x01(\x0b\x32\x17.build.buildgrid.Remote\x12-\n\x0cremote_asset\x18\x02 \x01(\x0b\x32\x17.build.buildgrid.Remote\x12-\n\x0c\x61\x63tion_cache\x18\x04 \x01(\x0b\x32\x17.build.buildgrid.Remote\":\n!GetInstanceNameForRemotesResponse\x12\x15\n\rinstance_name\x18\x01 \x01(\t\"I\n\"GetInstanceNameForNamespaceRequest\x12\x15\n\rinstance_name\x18\x01 \x01(\t\x12\x0c\n\x04root\x18\x02 \x01(\t\"<\n#GetInstanceNameForNamespaceResponse\x12\x15\n\rinstance_name\x18\x01 \x01(\t\"\x1a\n\x18GetLocalDiskUsageRequest\"D\n\x19GetLocalDiskUsageResponse\x12\x12\n\nsize_bytes\x18\x01 \x01(\x03\x12\x13\n\x0bquota_bytes\x18\x02 \x01(\x03\x32\xc9\t\n\x1eLocalContentAddressableStorage\x12l\n\x11\x46\x65tchMissingBlobs\x12).build.buildgrid.FetchMissingBlobsRequest\x1a*.build.buildgrid.FetchMissingBlobsResponse\"\x00\x12o\n\x12UploadMissingBlobs\x12*.build.buildgrid.UploadMissingBlobsRequest\x1a+.build.buildgrid.UploadMissingBlobsResponse\"\x00\x12T\n\tFetchTree\x12!.build.buildgrid.FetchTreeRequest\x1a\".build.buildgrid.FetchTreeResponse\"\x00\x12W\n\nUploadTree\x12\".build.buildgrid.UploadTreeRequest\x1a#.build.buildgrid.UploadTreeResponse\"\x00\x12X\n\tStageTree\x12!.build.buildgrid.StageTreeRequest\x1a\".build.buildgrid.StageTreeResponse\"\x00(\x01\x30\x01\x12Z\n\x0b\x43\x61ptureTree\x12#.build.buildgrid.CaptureTreeRequest\x1a$.build.buildgrid.CaptureTreeResponse\"\x00\x12]\n\x0c\x43\x61ptureFiles\x12$.build.buildgrid.CaptureFilesRequest\x1a%.build.buildgrid.CaptureFilesResponse\"\x00\x12\x81\x01\n\x18GetInstanceNameForRemote\x12\x30.build.buildgrid.GetInstanceNameForRemoteRequest\x1a\x31.build.buildgrid.GetInstanceNameForRemoteResponse\"\x00\x12\x84\x01\n\x19GetInstanceNameForRemotes\x12\x31.build.buildgrid.GetInstanceNameForRemotesRequest\x1a\x32.build.buildgrid.GetInstanceNameForRemotesResponse\"\x00\x12\x8a\x01\n\x1bGetInstanceNameForNamespace\x12\x33.build.buildgrid.GetInstanceNameForNamespaceRequest\x1a\x34.build.buildgrid.GetInstanceNameForNamespaceResponse\"\x00\x12l\n\x11GetLocalDiskUsage\x12).build.buildgrid.GetLocalDiskUsageRequest\x1a*.build.buildgrid.GetLocalDiskUsageResponse\"\x00\x62\x06proto3')



_FETCHMISSINGBLOBSREQUEST = DESCRIPTOR.message_types_by_name['FetchMissingBlobsRequest']
_FETCHMISSINGBLOBSRESPONSE = DESCRIPTOR.message_types_by_name['FetchMissingBlobsResponse']
_FETCHMISSINGBLOBSRESPONSE_RESPONSE = _FETCHMISSINGBLOBSRESPONSE.nested_types_by_name['Response']
_UPLOADMISSINGBLOBSREQUEST = DESCRIPTOR.message_types_by_name['UploadMissingBlobsRequest']
_UPLOADMISSINGBLOBSRESPONSE = DESCRIPTOR.message_types_by_name['UploadMissingBlobsResponse']
_UPLOADMISSINGBLOBSRESPONSE_RESPONSE = _UPLOADMISSINGBLOBSRESPONSE.nested_types_by_name['Response']
_FETCHTREEREQUEST = DESCRIPTOR.message_types_by_name['FetchTreeRequest']
_FETCHTREERESPONSE = DESCRIPTOR.message_types_by_name['FetchTreeResponse']
_UPLOADTREEREQUEST = DESCRIPTOR.message_types_by_name['UploadTreeRequest']
_UPLOADTREERESPONSE = DESCRIPTOR.message_types_by_name['UploadTreeResponse']
_STAGETREEREQUEST = DESCRIPTOR.message_types_by_name['StageTreeRequest']
_STAGETREEREQUEST_CREDENTIALS = _STAGETREEREQUEST.nested_types_by_name['Credentials']
_STAGETREERESPONSE = DESCRIPTOR.message_types_by_name['StageTreeResponse']
_CAPTURETREEREQUEST = DESCRIPTOR.message_types_by_name['CaptureTreeRequest']
_CAPTURETREERESPONSE = DESCRIPTOR.message_types_by_name['CaptureTreeResponse']
_CAPTURETREERESPONSE_RESPONSE = _CAPTURETREERESPONSE.nested_types_by_name['Response']
_CAPTUREFILESREQUEST = DESCRIPTOR.message_types_by_name['CaptureFilesRequest']
_CAPTUREFILESRESPONSE = DESCRIPTOR.message_types_by_name['CaptureFilesResponse']
_CAPTUREFILESRESPONSE_RESPONSE = _CAPTUREFILESRESPONSE.nested_types_by_name['Response']
_GETINSTANCENAMEFORREMOTEREQUEST = DESCRIPTOR.message_types_by_name['GetInstanceNameForRemoteRequest']
_GETINSTANCENAMEFORREMOTERESPONSE = DESCRIPTOR.message_types_by_name['GetInstanceNameForRemoteResponse']
_REMOTE = DESCRIPTOR.message_types_by_name['Remote']
_GETINSTANCENAMEFORREMOTESREQUEST = DESCRIPTOR.message_types_by_name['GetInstanceNameForRemotesRequest']
_GETINSTANCENAMEFORREMOTESRESPONSE = DESCRIPTOR.message_types_by_name['GetInstanceNameForRemotesResponse']
_GETINSTANCENAMEFORNAMESPACEREQUEST = DESCRIPTOR.message_types_by_name['GetInstanceNameForNamespaceRequest']
_GETINSTANCENAMEFORNAMESPACERESPONSE = DESCRIPTOR.message_types_by_name['GetInstanceNameForNamespaceResponse']
_GETLOCALDISKUSAGEREQUEST = DESCRIPTOR.message_types_by_name['GetLocalDiskUsageRequest']
_GETLOCALDISKUSAGERESPONSE = DESCRIPTOR.message_types_by_name['GetLocalDiskUsageResponse']
FetchMissingBlobsRequest = _reflection.GeneratedProtocolMessageType('FetchMissingBlobsRequest', (_message.Message,), {
  'DESCRIPTOR' : _FETCHMISSINGBLOBSREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.FetchMissingBlobsRequest)
  })
_sym_db.RegisterMessage(FetchMissingBlobsRequest)

FetchMissingBlobsResponse = _reflection.GeneratedProtocolMessageType('FetchMissingBlobsResponse', (_message.Message,), {

  'Response' : _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), {
    'DESCRIPTOR' : _FETCHMISSINGBLOBSRESPONSE_RESPONSE,
    '__module__' : 'build.buildgrid.local_cas_pb2'
    # @@protoc_insertion_point(class_scope:build.buildgrid.FetchMissingBlobsResponse.Response)
    })
  ,
  'DESCRIPTOR' : _FETCHMISSINGBLOBSRESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.FetchMissingBlobsResponse)
  })
_sym_db.RegisterMessage(FetchMissingBlobsResponse)
_sym_db.RegisterMessage(FetchMissingBlobsResponse.Response)

UploadMissingBlobsRequest = _reflection.GeneratedProtocolMessageType('UploadMissingBlobsRequest', (_message.Message,), {
  'DESCRIPTOR' : _UPLOADMISSINGBLOBSREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.UploadMissingBlobsRequest)
  })
_sym_db.RegisterMessage(UploadMissingBlobsRequest)

UploadMissingBlobsResponse = _reflection.GeneratedProtocolMessageType('UploadMissingBlobsResponse', (_message.Message,), {

  'Response' : _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), {
    'DESCRIPTOR' : _UPLOADMISSINGBLOBSRESPONSE_RESPONSE,
    '__module__' : 'build.buildgrid.local_cas_pb2'
    # @@protoc_insertion_point(class_scope:build.buildgrid.UploadMissingBlobsResponse.Response)
    })
  ,
  'DESCRIPTOR' : _UPLOADMISSINGBLOBSRESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.UploadMissingBlobsResponse)
  })
_sym_db.RegisterMessage(UploadMissingBlobsResponse)
_sym_db.RegisterMessage(UploadMissingBlobsResponse.Response)

FetchTreeRequest = _reflection.GeneratedProtocolMessageType('FetchTreeRequest', (_message.Message,), {
  'DESCRIPTOR' : _FETCHTREEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.FetchTreeRequest)
  })
_sym_db.RegisterMessage(FetchTreeRequest)

FetchTreeResponse = _reflection.GeneratedProtocolMessageType('FetchTreeResponse', (_message.Message,), {
  'DESCRIPTOR' : _FETCHTREERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.FetchTreeResponse)
  })
_sym_db.RegisterMessage(FetchTreeResponse)

UploadTreeRequest = _reflection.GeneratedProtocolMessageType('UploadTreeRequest', (_message.Message,), {
  'DESCRIPTOR' : _UPLOADTREEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.UploadTreeRequest)
  })
_sym_db.RegisterMessage(UploadTreeRequest)

UploadTreeResponse = _reflection.GeneratedProtocolMessageType('UploadTreeResponse', (_message.Message,), {
  'DESCRIPTOR' : _UPLOADTREERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.UploadTreeResponse)
  })
_sym_db.RegisterMessage(UploadTreeResponse)

StageTreeRequest = _reflection.GeneratedProtocolMessageType('StageTreeRequest', (_message.Message,), {

  'Credentials' : _reflection.GeneratedProtocolMessageType('Credentials', (_message.Message,), {
    'DESCRIPTOR' : _STAGETREEREQUEST_CREDENTIALS,
    '__module__' : 'build.buildgrid.local_cas_pb2'
    # @@protoc_insertion_point(class_scope:build.buildgrid.StageTreeRequest.Credentials)
    })
  ,
  'DESCRIPTOR' : _STAGETREEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.StageTreeRequest)
  })
_sym_db.RegisterMessage(StageTreeRequest)
_sym_db.RegisterMessage(StageTreeRequest.Credentials)

StageTreeResponse = _reflection.GeneratedProtocolMessageType('StageTreeResponse', (_message.Message,), {
  'DESCRIPTOR' : _STAGETREERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.StageTreeResponse)
  })
_sym_db.RegisterMessage(StageTreeResponse)

CaptureTreeRequest = _reflection.GeneratedProtocolMessageType('CaptureTreeRequest', (_message.Message,), {
  'DESCRIPTOR' : _CAPTURETREEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.CaptureTreeRequest)
  })
_sym_db.RegisterMessage(CaptureTreeRequest)

CaptureTreeResponse = _reflection.GeneratedProtocolMessageType('CaptureTreeResponse', (_message.Message,), {

  'Response' : _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), {
    'DESCRIPTOR' : _CAPTURETREERESPONSE_RESPONSE,
    '__module__' : 'build.buildgrid.local_cas_pb2'
    # @@protoc_insertion_point(class_scope:build.buildgrid.CaptureTreeResponse.Response)
    })
  ,
  'DESCRIPTOR' : _CAPTURETREERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.CaptureTreeResponse)
  })
_sym_db.RegisterMessage(CaptureTreeResponse)
_sym_db.RegisterMessage(CaptureTreeResponse.Response)

CaptureFilesRequest = _reflection.GeneratedProtocolMessageType('CaptureFilesRequest', (_message.Message,), {
  'DESCRIPTOR' : _CAPTUREFILESREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.CaptureFilesRequest)
  })
_sym_db.RegisterMessage(CaptureFilesRequest)

CaptureFilesResponse = _reflection.GeneratedProtocolMessageType('CaptureFilesResponse', (_message.Message,), {

  'Response' : _reflection.GeneratedProtocolMessageType('Response', (_message.Message,), {
    'DESCRIPTOR' : _CAPTUREFILESRESPONSE_RESPONSE,
    '__module__' : 'build.buildgrid.local_cas_pb2'
    # @@protoc_insertion_point(class_scope:build.buildgrid.CaptureFilesResponse.Response)
    })
  ,
  'DESCRIPTOR' : _CAPTUREFILESRESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.CaptureFilesResponse)
  })
_sym_db.RegisterMessage(CaptureFilesResponse)
_sym_db.RegisterMessage(CaptureFilesResponse.Response)

GetInstanceNameForRemoteRequest = _reflection.GeneratedProtocolMessageType('GetInstanceNameForRemoteRequest', (_message.Message,), {
  'DESCRIPTOR' : _GETINSTANCENAMEFORREMOTEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetInstanceNameForRemoteRequest)
  })
_sym_db.RegisterMessage(GetInstanceNameForRemoteRequest)

GetInstanceNameForRemoteResponse = _reflection.GeneratedProtocolMessageType('GetInstanceNameForRemoteResponse', (_message.Message,), {
  'DESCRIPTOR' : _GETINSTANCENAMEFORREMOTERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetInstanceNameForRemoteResponse)
  })
_sym_db.RegisterMessage(GetInstanceNameForRemoteResponse)

Remote = _reflection.GeneratedProtocolMessageType('Remote', (_message.Message,), {
  'DESCRIPTOR' : _REMOTE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.Remote)
  })
_sym_db.RegisterMessage(Remote)

GetInstanceNameForRemotesRequest = _reflection.GeneratedProtocolMessageType('GetInstanceNameForRemotesRequest', (_message.Message,), {
  'DESCRIPTOR' : _GETINSTANCENAMEFORREMOTESREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetInstanceNameForRemotesRequest)
  })
_sym_db.RegisterMessage(GetInstanceNameForRemotesRequest)

GetInstanceNameForRemotesResponse = _reflection.GeneratedProtocolMessageType('GetInstanceNameForRemotesResponse', (_message.Message,), {
  'DESCRIPTOR' : _GETINSTANCENAMEFORREMOTESRESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetInstanceNameForRemotesResponse)
  })
_sym_db.RegisterMessage(GetInstanceNameForRemotesResponse)

GetInstanceNameForNamespaceRequest = _reflection.GeneratedProtocolMessageType('GetInstanceNameForNamespaceRequest', (_message.Message,), {
  'DESCRIPTOR' : _GETINSTANCENAMEFORNAMESPACEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetInstanceNameForNamespaceRequest)
  })
_sym_db.RegisterMessage(GetInstanceNameForNamespaceRequest)

GetInstanceNameForNamespaceResponse = _reflection.GeneratedProtocolMessageType('GetInstanceNameForNamespaceResponse', (_message.Message,), {
  'DESCRIPTOR' : _GETINSTANCENAMEFORNAMESPACERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetInstanceNameForNamespaceResponse)
  })
_sym_db.RegisterMessage(GetInstanceNameForNamespaceResponse)

GetLocalDiskUsageRequest = _reflection.GeneratedProtocolMessageType('GetLocalDiskUsageRequest', (_message.Message,), {
  'DESCRIPTOR' : _GETLOCALDISKUSAGEREQUEST,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetLocalDiskUsageRequest)
  })
_sym_db.RegisterMessage(GetLocalDiskUsageRequest)

GetLocalDiskUsageResponse = _reflection.GeneratedProtocolMessageType('GetLocalDiskUsageResponse', (_message.Message,), {
  'DESCRIPTOR' : _GETLOCALDISKUSAGERESPONSE,
  '__module__' : 'build.buildgrid.local_cas_pb2'
  # @@protoc_insertion_point(class_scope:build.buildgrid.GetLocalDiskUsageResponse)
  })
_sym_db.RegisterMessage(GetLocalDiskUsageResponse)

_LOCALCONTENTADDRESSABLESTORAGE = DESCRIPTOR.services_by_name['LocalContentAddressableStorage']
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _FETCHMISSINGBLOBSREQUEST._serialized_start=133
  _FETCHMISSINGBLOBSREQUEST._serialized_end=245
  _FETCHMISSINGBLOBSRESPONSE._serialized_start=248
  _FETCHMISSINGBLOBSRESPONSE._serialized_end=452
  _FETCHMISSINGBLOBSRESPONSE_RESPONSE._serialized_start=349
  _FETCHMISSINGBLOBSRESPONSE_RESPONSE._serialized_end=452
  _UPLOADMISSINGBLOBSREQUEST._serialized_start=454
  _UPLOADMISSINGBLOBSREQUEST._serialized_end=567
  _UPLOADMISSINGBLOBSRESPONSE._serialized_start=570
  _UPLOADMISSINGBLOBSRESPONSE._serialized_end=776
  _UPLOADMISSINGBLOBSRESPONSE_RESPONSE._serialized_start=349
  _UPLOADMISSINGBLOBSRESPONSE_RESPONSE._serialized_end=452
  _FETCHTREEREQUEST._serialized_start=779
  _FETCHTREEREQUEST._serialized_end=908
  _FETCHTREERESPONSE._serialized_start=910
  _FETCHTREERESPONSE._serialized_end=929
  _UPLOADTREEREQUEST._serialized_start=931
  _UPLOADTREEREQUEST._serialized_end=1035
  _UPLOADTREERESPONSE._serialized_start=1037
  _UPLOADTREERESPONSE._serialized_end=1057
  _STAGETREEREQUEST._serialized_start=1060
  _STAGETREEREQUEST._serialized_end=1280
  _STAGETREEREQUEST_CREDENTIALS._serialized_start=1254
  _STAGETREEREQUEST_CREDENTIALS._serialized_end=1280
  _STAGETREERESPONSE._serialized_start=1282
  _STAGETREERESPONSE._serialized_end=1315
  _CAPTURETREEREQUEST._serialized_start=1318
  _CAPTURETREEREQUEST._serialized_end=1462
  _CAPTURETREERESPONSE._serialized_start=1465
  _CAPTURETREERESPONSE._serialized_end=1676
  _CAPTURETREERESPONSE_RESPONSE._serialized_start=1554
  _CAPTURETREERESPONSE_RESPONSE._serialized_end=1676
  _CAPTUREFILESREQUEST._serialized_start=1679
  _CAPTUREFILESREQUEST._serialized_end=1824
  _CAPTUREFILESRESPONSE._serialized_start=1827
  _CAPTUREFILESRESPONSE._serialized_end=2139
  _CAPTUREFILESRESPONSE_RESPONSE._serialized_start=1919
  _CAPTUREFILESRESPONSE_RESPONSE._serialized_end=2139
  _GETINSTANCENAMEFORREMOTEREQUEST._serialized_start=2142
  _GETINSTANCENAMEFORREMOTEREQUEST._serialized_end=2273
  _GETINSTANCENAMEFORREMOTERESPONSE._serialized_start=2275
  _GETINSTANCENAMEFORREMOTERESPONSE._serialized_end=2332
  _REMOTE._serialized_start=2334
  _REMOTE._serialized_end=2440
  _GETINSTANCENAMEFORREMOTESREQUEST._serialized_start=2443
  _GETINSTANCENAMEFORREMOTESREQUEST._serialized_end=2656
  _GETINSTANCENAMEFORREMOTESRESPONSE._serialized_start=2658
  _GETINSTANCENAMEFORREMOTESRESPONSE._serialized_end=2716
  _GETINSTANCENAMEFORNAMESPACEREQUEST._serialized_start=2718
  _GETINSTANCENAMEFORNAMESPACEREQUEST._serialized_end=2791
  _GETINSTANCENAMEFORNAMESPACERESPONSE._serialized_start=2793
  _GETINSTANCENAMEFORNAMESPACERESPONSE._serialized_end=2853
  _GETLOCALDISKUSAGEREQUEST._serialized_start=2855
  _GETLOCALDISKUSAGEREQUEST._serialized_end=2881
  _GETLOCALDISKUSAGERESPONSE._serialized_start=2883
  _GETLOCALDISKUSAGERESPONSE._serialized_end=2951
  _LOCALCONTENTADDRESSABLESTORAGE._serialized_start=2954
  _LOCALCONTENTADDRESSABLESTORAGE._serialized_end=4179
# @@protoc_insertion_point(module_scope)
