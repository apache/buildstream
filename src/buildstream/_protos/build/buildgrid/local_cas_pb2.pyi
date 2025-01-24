from build.bazel.remote.execution.v2 import remote_execution_pb2 as _remote_execution_pb2
from google.rpc import status_pb2 as _status_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FetchMissingBlobsRequest(_message.Message):
    __slots__ = ("instance_name", "blob_digests")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    BLOB_DIGESTS_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    blob_digests: _containers.RepeatedCompositeFieldContainer[_remote_execution_pb2.Digest]
    def __init__(self, instance_name: _Optional[str] = ..., blob_digests: _Optional[_Iterable[_Union[_remote_execution_pb2.Digest, _Mapping]]] = ...) -> None: ...

class FetchMissingBlobsResponse(_message.Message):
    __slots__ = ("responses",)
    class Response(_message.Message):
        __slots__ = ("digest", "status")
        DIGEST_FIELD_NUMBER: _ClassVar[int]
        STATUS_FIELD_NUMBER: _ClassVar[int]
        digest: _remote_execution_pb2.Digest
        status: _status_pb2.Status
        def __init__(self, digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., status: _Optional[_Union[_status_pb2.Status, _Mapping]] = ...) -> None: ...
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[FetchMissingBlobsResponse.Response]
    def __init__(self, responses: _Optional[_Iterable[_Union[FetchMissingBlobsResponse.Response, _Mapping]]] = ...) -> None: ...

class UploadMissingBlobsRequest(_message.Message):
    __slots__ = ("instance_name", "blob_digests")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    BLOB_DIGESTS_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    blob_digests: _containers.RepeatedCompositeFieldContainer[_remote_execution_pb2.Digest]
    def __init__(self, instance_name: _Optional[str] = ..., blob_digests: _Optional[_Iterable[_Union[_remote_execution_pb2.Digest, _Mapping]]] = ...) -> None: ...

class UploadMissingBlobsResponse(_message.Message):
    __slots__ = ("responses",)
    class Response(_message.Message):
        __slots__ = ("digest", "status")
        DIGEST_FIELD_NUMBER: _ClassVar[int]
        STATUS_FIELD_NUMBER: _ClassVar[int]
        digest: _remote_execution_pb2.Digest
        status: _status_pb2.Status
        def __init__(self, digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., status: _Optional[_Union[_status_pb2.Status, _Mapping]] = ...) -> None: ...
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[UploadMissingBlobsResponse.Response]
    def __init__(self, responses: _Optional[_Iterable[_Union[UploadMissingBlobsResponse.Response, _Mapping]]] = ...) -> None: ...

class FetchTreeRequest(_message.Message):
    __slots__ = ("instance_name", "root_digest", "fetch_file_blobs")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROOT_DIGEST_FIELD_NUMBER: _ClassVar[int]
    FETCH_FILE_BLOBS_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    root_digest: _remote_execution_pb2.Digest
    fetch_file_blobs: bool
    def __init__(self, instance_name: _Optional[str] = ..., root_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., fetch_file_blobs: bool = ...) -> None: ...

class FetchTreeResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class UploadTreeRequest(_message.Message):
    __slots__ = ("instance_name", "root_digest")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROOT_DIGEST_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    root_digest: _remote_execution_pb2.Digest
    def __init__(self, instance_name: _Optional[str] = ..., root_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ...) -> None: ...

class UploadTreeResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StageTreeRequest(_message.Message):
    __slots__ = ("instance_name", "root_digest", "path", "access_credentials")
    class Credentials(_message.Message):
        __slots__ = ("uid", "gid")
        UID_FIELD_NUMBER: _ClassVar[int]
        GID_FIELD_NUMBER: _ClassVar[int]
        uid: int
        gid: int
        def __init__(self, uid: _Optional[int] = ..., gid: _Optional[int] = ...) -> None: ...
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROOT_DIGEST_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    ACCESS_CREDENTIALS_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    root_digest: _remote_execution_pb2.Digest
    path: str
    access_credentials: StageTreeRequest.Credentials
    def __init__(self, instance_name: _Optional[str] = ..., root_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., path: _Optional[str] = ..., access_credentials: _Optional[_Union[StageTreeRequest.Credentials, _Mapping]] = ...) -> None: ...

class StageTreeResponse(_message.Message):
    __slots__ = ("path",)
    PATH_FIELD_NUMBER: _ClassVar[int]
    path: str
    def __init__(self, path: _Optional[str] = ...) -> None: ...

class CaptureTreeRequest(_message.Message):
    __slots__ = ("instance_name", "root", "path", "bypass_local_cache", "node_properties", "move_files", "output_directory_format", "skip_upload")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROOT_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    BYPASS_LOCAL_CACHE_FIELD_NUMBER: _ClassVar[int]
    NODE_PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    MOVE_FILES_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_DIRECTORY_FORMAT_FIELD_NUMBER: _ClassVar[int]
    SKIP_UPLOAD_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    root: str
    path: _containers.RepeatedScalarFieldContainer[str]
    bypass_local_cache: bool
    node_properties: _containers.RepeatedScalarFieldContainer[str]
    move_files: bool
    output_directory_format: _remote_execution_pb2.Command.OutputDirectoryFormat
    skip_upload: bool
    def __init__(self, instance_name: _Optional[str] = ..., root: _Optional[str] = ..., path: _Optional[_Iterable[str]] = ..., bypass_local_cache: bool = ..., node_properties: _Optional[_Iterable[str]] = ..., move_files: bool = ..., output_directory_format: _Optional[_Union[_remote_execution_pb2.Command.OutputDirectoryFormat, str]] = ..., skip_upload: bool = ...) -> None: ...

class CaptureTreeResponse(_message.Message):
    __slots__ = ("responses",)
    class Response(_message.Message):
        __slots__ = ("path", "tree_digest", "status", "root_directory_digest")
        PATH_FIELD_NUMBER: _ClassVar[int]
        TREE_DIGEST_FIELD_NUMBER: _ClassVar[int]
        STATUS_FIELD_NUMBER: _ClassVar[int]
        ROOT_DIRECTORY_DIGEST_FIELD_NUMBER: _ClassVar[int]
        path: str
        tree_digest: _remote_execution_pb2.Digest
        status: _status_pb2.Status
        root_directory_digest: _remote_execution_pb2.Digest
        def __init__(self, path: _Optional[str] = ..., tree_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., status: _Optional[_Union[_status_pb2.Status, _Mapping]] = ..., root_directory_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ...) -> None: ...
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[CaptureTreeResponse.Response]
    def __init__(self, responses: _Optional[_Iterable[_Union[CaptureTreeResponse.Response, _Mapping]]] = ...) -> None: ...

class CaptureFilesRequest(_message.Message):
    __slots__ = ("instance_name", "root", "path", "bypass_local_cache", "node_properties", "move_files", "skip_upload")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROOT_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    BYPASS_LOCAL_CACHE_FIELD_NUMBER: _ClassVar[int]
    NODE_PROPERTIES_FIELD_NUMBER: _ClassVar[int]
    MOVE_FILES_FIELD_NUMBER: _ClassVar[int]
    SKIP_UPLOAD_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    root: str
    path: _containers.RepeatedScalarFieldContainer[str]
    bypass_local_cache: bool
    node_properties: _containers.RepeatedScalarFieldContainer[str]
    move_files: bool
    skip_upload: bool
    def __init__(self, instance_name: _Optional[str] = ..., root: _Optional[str] = ..., path: _Optional[_Iterable[str]] = ..., bypass_local_cache: bool = ..., node_properties: _Optional[_Iterable[str]] = ..., move_files: bool = ..., skip_upload: bool = ...) -> None: ...

class CaptureFilesResponse(_message.Message):
    __slots__ = ("responses",)
    class Response(_message.Message):
        __slots__ = ("path", "digest", "status", "is_executable", "node_properties")
        PATH_FIELD_NUMBER: _ClassVar[int]
        DIGEST_FIELD_NUMBER: _ClassVar[int]
        STATUS_FIELD_NUMBER: _ClassVar[int]
        IS_EXECUTABLE_FIELD_NUMBER: _ClassVar[int]
        NODE_PROPERTIES_FIELD_NUMBER: _ClassVar[int]
        path: str
        digest: _remote_execution_pb2.Digest
        status: _status_pb2.Status
        is_executable: bool
        node_properties: _remote_execution_pb2.NodeProperties
        def __init__(self, path: _Optional[str] = ..., digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., status: _Optional[_Union[_status_pb2.Status, _Mapping]] = ..., is_executable: bool = ..., node_properties: _Optional[_Union[_remote_execution_pb2.NodeProperties, _Mapping]] = ...) -> None: ...
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[CaptureFilesResponse.Response]
    def __init__(self, responses: _Optional[_Iterable[_Union[CaptureFilesResponse.Response, _Mapping]]] = ...) -> None: ...

class GetInstanceNameForRemoteRequest(_message.Message):
    __slots__ = ("url", "instance_name", "server_cert", "client_key", "client_cert")
    URL_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    SERVER_CERT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_KEY_FIELD_NUMBER: _ClassVar[int]
    CLIENT_CERT_FIELD_NUMBER: _ClassVar[int]
    url: str
    instance_name: str
    server_cert: bytes
    client_key: bytes
    client_cert: bytes
    def __init__(self, url: _Optional[str] = ..., instance_name: _Optional[str] = ..., server_cert: _Optional[bytes] = ..., client_key: _Optional[bytes] = ..., client_cert: _Optional[bytes] = ...) -> None: ...

class GetInstanceNameForRemoteResponse(_message.Message):
    __slots__ = ("instance_name",)
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    def __init__(self, instance_name: _Optional[str] = ...) -> None: ...

class Remote(_message.Message):
    __slots__ = ("url", "instance_name", "server_cert", "client_key", "client_cert", "access_token_path", "access_token_reload_interval", "keepalive_time", "retry_limit", "retry_delay", "request_timeout")
    URL_FIELD_NUMBER: _ClassVar[int]
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    SERVER_CERT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_KEY_FIELD_NUMBER: _ClassVar[int]
    CLIENT_CERT_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_PATH_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_RELOAD_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    KEEPALIVE_TIME_FIELD_NUMBER: _ClassVar[int]
    RETRY_LIMIT_FIELD_NUMBER: _ClassVar[int]
    RETRY_DELAY_FIELD_NUMBER: _ClassVar[int]
    REQUEST_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    url: str
    instance_name: str
    server_cert: bytes
    client_key: bytes
    client_cert: bytes
    access_token_path: str
    access_token_reload_interval: _duration_pb2.Duration
    keepalive_time: _duration_pb2.Duration
    retry_limit: int
    retry_delay: _duration_pb2.Duration
    request_timeout: _duration_pb2.Duration
    def __init__(self, url: _Optional[str] = ..., instance_name: _Optional[str] = ..., server_cert: _Optional[bytes] = ..., client_key: _Optional[bytes] = ..., client_cert: _Optional[bytes] = ..., access_token_path: _Optional[str] = ..., access_token_reload_interval: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ..., keepalive_time: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ..., retry_limit: _Optional[int] = ..., retry_delay: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ..., request_timeout: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ...) -> None: ...

class GetInstanceNameForRemotesRequest(_message.Message):
    __slots__ = ("instance_name", "content_addressable_storage", "remote_asset", "action_cache", "execution")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    CONTENT_ADDRESSABLE_STORAGE_FIELD_NUMBER: _ClassVar[int]
    REMOTE_ASSET_FIELD_NUMBER: _ClassVar[int]
    ACTION_CACHE_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    content_addressable_storage: Remote
    remote_asset: Remote
    action_cache: Remote
    execution: Remote
    def __init__(self, instance_name: _Optional[str] = ..., content_addressable_storage: _Optional[_Union[Remote, _Mapping]] = ..., remote_asset: _Optional[_Union[Remote, _Mapping]] = ..., action_cache: _Optional[_Union[Remote, _Mapping]] = ..., execution: _Optional[_Union[Remote, _Mapping]] = ...) -> None: ...

class GetInstanceNameForRemotesResponse(_message.Message):
    __slots__ = ("instance_name",)
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    def __init__(self, instance_name: _Optional[str] = ...) -> None: ...

class GetInstanceNameForNamespaceRequest(_message.Message):
    __slots__ = ("instance_name", "root")
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    ROOT_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    root: str
    def __init__(self, instance_name: _Optional[str] = ..., root: _Optional[str] = ...) -> None: ...

class GetInstanceNameForNamespaceResponse(_message.Message):
    __slots__ = ("instance_name",)
    INSTANCE_NAME_FIELD_NUMBER: _ClassVar[int]
    instance_name: str
    def __init__(self, instance_name: _Optional[str] = ...) -> None: ...

class GetLocalDiskUsageRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetLocalDiskUsageResponse(_message.Message):
    __slots__ = ("size_bytes", "quota_bytes")
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    QUOTA_BYTES_FIELD_NUMBER: _ClassVar[int]
    size_bytes: int
    quota_bytes: int
    def __init__(self, size_bytes: _Optional[int] = ..., quota_bytes: _Optional[int] = ...) -> None: ...
