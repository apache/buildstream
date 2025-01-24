from build.bazel.remote.execution.v2 import remote_execution_pb2 as _remote_execution_pb2
from google.api import annotations_pb2 as _annotations_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.rpc import status_pb2 as _status_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Qualifier(_message.Message):
    __slots__ = ("name", "value")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: str
    def __init__(self, name: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class FetchBlobRequest(_message.Message):
    __slots__ = ("instance_name", "timeout", "oldest_content_accepted", "uris", "qualifiers", "digest_function")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    OLDEST_CONTENT_ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    URIS_FIELD_NUMBER: _ClassVar[int]
    QUALIFIERS_FIELD_NUMBER: _ClassVar[int]
    DIGEST_FUNCTION_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    timeout: _duration_pb2.Duration
    oldest_content_accepted: _timestamp_pb2.Timestamp
    uris: _containers.RepeatedScalarFieldContainer[str]
    qualifiers: _containers.RepeatedCompositeFieldContainer[Qualifier]
    digest_function: _remote_execution_pb2.DigestFunction.Value
    def __init__(self, instance_name: _Optional[str] = ..., timeout: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ..., oldest_content_accepted: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., uris: _Optional[_Iterable[str]] = ..., qualifiers: _Optional[_Iterable[_Union[Qualifier, _Mapping]]] = ..., digest_function: _Optional[_Union[_remote_execution_pb2.DigestFunction.Value, str]] = ...) -> None: ...

class FetchBlobResponse(_message.Message):
    __slots__ = ("status", "uri", "qualifiers", "expires_at", "blob_digest", "digest_function")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    URI_FIELD_NUMBER: _ClassVar[int]
    QUALIFIERS_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    BLOB_DIGEST_FIELD_NUMBER: _ClassVar[int]
    DIGEST_FUNCTION_FIELD_NUMBER: _ClassVar[int]
    status: _status_pb2.Status
    uri: str
    qualifiers: _containers.RepeatedCompositeFieldContainer[Qualifier]
    expires_at: _timestamp_pb2.Timestamp
    blob_digest: _remote_execution_pb2.Digest
    digest_function: _remote_execution_pb2.DigestFunction.Value
    def __init__(self, status: _Optional[_Union[_status_pb2.Status, _Mapping]] = ..., uri: _Optional[str] = ..., qualifiers: _Optional[_Iterable[_Union[Qualifier, _Mapping]]] = ..., expires_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., blob_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., digest_function: _Optional[_Union[_remote_execution_pb2.DigestFunction.Value, str]] = ...) -> None: ...

class FetchDirectoryRequest(_message.Message):
    __slots__ = ("instance_name", "timeout", "oldest_content_accepted", "uris", "qualifiers", "digest_function")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    OLDEST_CONTENT_ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    URIS_FIELD_NUMBER: _ClassVar[int]
    QUALIFIERS_FIELD_NUMBER: _ClassVar[int]
    DIGEST_FUNCTION_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    timeout: _duration_pb2.Duration
    oldest_content_accepted: _timestamp_pb2.Timestamp
    uris: _containers.RepeatedScalarFieldContainer[str]
    qualifiers: _containers.RepeatedCompositeFieldContainer[Qualifier]
    digest_function: _remote_execution_pb2.DigestFunction.Value
    def __init__(self, instance_name: _Optional[str] = ..., timeout: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ..., oldest_content_accepted: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., uris: _Optional[_Iterable[str]] = ..., qualifiers: _Optional[_Iterable[_Union[Qualifier, _Mapping]]] = ..., digest_function: _Optional[_Union[_remote_execution_pb2.DigestFunction.Value, str]] = ...) -> None: ...

class FetchDirectoryResponse(_message.Message):
    __slots__ = ("status", "uri", "qualifiers", "expires_at", "root_directory_digest", "digest_function")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    URI_FIELD_NUMBER: _ClassVar[int]
    QUALIFIERS_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    ROOT_DIRECTORY_DIGEST_FIELD_NUMBER: _ClassVar[int]
    DIGEST_FUNCTION_FIELD_NUMBER: _ClassVar[int]
    status: _status_pb2.Status
    uri: str
    qualifiers: _containers.RepeatedCompositeFieldContainer[Qualifier]
    expires_at: _timestamp_pb2.Timestamp
    root_directory_digest: _remote_execution_pb2.Digest
    digest_function: _remote_execution_pb2.DigestFunction.Value
    def __init__(self, status: _Optional[_Union[_status_pb2.Status, _Mapping]] = ..., uri: _Optional[str] = ..., qualifiers: _Optional[_Iterable[_Union[Qualifier, _Mapping]]] = ..., expires_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., root_directory_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., digest_function: _Optional[_Union[_remote_execution_pb2.DigestFunction.Value, str]] = ...) -> None: ...

class PushBlobRequest(_message.Message):
    __slots__ = ("instance_name", "uris", "qualifiers", "expire_at", "blob_digest", "references_blobs", "references_directories", "digest_function")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    URIS_FIELD_NUMBER: _ClassVar[int]
    QUALIFIERS_FIELD_NUMBER: _ClassVar[int]
    EXPIRE_AT_FIELD_NUMBER: _ClassVar[int]
    BLOB_DIGEST_FIELD_NUMBER: _ClassVar[int]
    REFERENCES_BLOBS_FIELD_NUMBER: _ClassVar[int]
    REFERENCES_DIRECTORIES_FIELD_NUMBER: _ClassVar[int]
    DIGEST_FUNCTION_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    uris: _containers.RepeatedScalarFieldContainer[str]
    qualifiers: _containers.RepeatedCompositeFieldContainer[Qualifier]
    expire_at: _timestamp_pb2.Timestamp
    blob_digest: _remote_execution_pb2.Digest
    references_blobs: _containers.RepeatedCompositeFieldContainer[_remote_execution_pb2.Digest]
    references_directories: _containers.RepeatedCompositeFieldContainer[_remote_execution_pb2.Digest]
    digest_function: _remote_execution_pb2.DigestFunction.Value
    def __init__(self, instance_name: _Optional[str] = ..., uris: _Optional[_Iterable[str]] = ..., qualifiers: _Optional[_Iterable[_Union[Qualifier, _Mapping]]] = ..., expire_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., blob_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., references_blobs: _Optional[_Iterable[_Union[_remote_execution_pb2.Digest, _Mapping]]] = ..., references_directories: _Optional[_Iterable[_Union[_remote_execution_pb2.Digest, _Mapping]]] = ..., digest_function: _Optional[_Union[_remote_execution_pb2.DigestFunction.Value, str]] = ...) -> None: ...

class PushBlobResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class PushDirectoryRequest(_message.Message):
    __slots__ = ("instance_name", "uris", "qualifiers", "expire_at", "root_directory_digest", "references_blobs", "references_directories", "digest_function")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    URIS_FIELD_NUMBER: _ClassVar[int]
    QUALIFIERS_FIELD_NUMBER: _ClassVar[int]
    EXPIRE_AT_FIELD_NUMBER: _ClassVar[int]
    ROOT_DIRECTORY_DIGEST_FIELD_NUMBER: _ClassVar[int]
    REFERENCES_BLOBS_FIELD_NUMBER: _ClassVar[int]
    REFERENCES_DIRECTORIES_FIELD_NUMBER: _ClassVar[int]
    DIGEST_FUNCTION_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    uris: _containers.RepeatedScalarFieldContainer[str]
    qualifiers: _containers.RepeatedCompositeFieldContainer[Qualifier]
    expire_at: _timestamp_pb2.Timestamp
    root_directory_digest: _remote_execution_pb2.Digest
    references_blobs: _containers.RepeatedCompositeFieldContainer[_remote_execution_pb2.Digest]
    references_directories: _containers.RepeatedCompositeFieldContainer[_remote_execution_pb2.Digest]
    digest_function: _remote_execution_pb2.DigestFunction.Value
    def __init__(self, instance_name: _Optional[str] = ..., uris: _Optional[_Iterable[str]] = ..., qualifiers: _Optional[_Iterable[_Union[Qualifier, _Mapping]]] = ..., expire_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., root_directory_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., references_blobs: _Optional[_Iterable[_Union[_remote_execution_pb2.Digest, _Mapping]]] = ..., references_directories: _Optional[_Iterable[_Union[_remote_execution_pb2.Digest, _Mapping]]] = ..., digest_function: _Optional[_Union[_remote_execution_pb2.DigestFunction.Value, str]] = ...) -> None: ...

class PushDirectoryResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
