from build.bazel.remote.execution.v2 import remote_execution_pb2 as _remote_execution_pb2
from google.api import annotations_pb2 as _annotations_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Artifact(_message.Message):
    __slots__ = ("version", "build_success", "build_error", "build_error_details", "strong_key", "weak_key", "was_workspaced", "files", "build_deps", "public_data", "logs", "buildtree", "sources", "low_diversity_meta", "high_diversity_meta", "strict_key", "buildroot")
    class Dependency(_message.Message):
        __slots__ = ("project_name", "element_name", "cache_key", "was_workspaced")
        PROJECT_NAME_FIELD_NUMBER: _ClassVar[int]
        ELEMENT_NAME_FIELD_NUMBER: _ClassVar[int]
        CACHE_KEY_FIELD_NUMBER: _ClassVar[int]
        WAS_WORKSPACED_FIELD_NUMBER: _ClassVar[int]
        project_name: str
        element_name: str
        cache_key: str
        was_workspaced: bool
        def __init__(self, project_name: _Optional[str] = ..., element_name: _Optional[str] = ..., cache_key: _Optional[str] = ..., was_workspaced: bool = ...) -> None: ...
    class LogFile(_message.Message):
        __slots__ = ("name", "digest")
        NAME_FIELD_NUMBER: _ClassVar[int]
        DIGEST_FIELD_NUMBER: _ClassVar[int]
        name: str
        digest: _remote_execution_pb2.Digest
        def __init__(self, name: _Optional[str] = ..., digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ...) -> None: ...
    VERSION_FIELD_NUMBER: _ClassVar[int]
    BUILD_SUCCESS_FIELD_NUMBER: _ClassVar[int]
    BUILD_ERROR_FIELD_NUMBER: _ClassVar[int]
    BUILD_ERROR_DETAILS_FIELD_NUMBER: _ClassVar[int]
    STRONG_KEY_FIELD_NUMBER: _ClassVar[int]
    WEAK_KEY_FIELD_NUMBER: _ClassVar[int]
    WAS_WORKSPACED_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    BUILD_DEPS_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_DATA_FIELD_NUMBER: _ClassVar[int]
    LOGS_FIELD_NUMBER: _ClassVar[int]
    BUILDTREE_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    LOW_DIVERSITY_META_FIELD_NUMBER: _ClassVar[int]
    HIGH_DIVERSITY_META_FIELD_NUMBER: _ClassVar[int]
    STRICT_KEY_FIELD_NUMBER: _ClassVar[int]
    BUILDROOT_FIELD_NUMBER: _ClassVar[int]
    version: int
    build_success: bool
    build_error: str
    build_error_details: str
    strong_key: str
    weak_key: str
    was_workspaced: bool
    files: _remote_execution_pb2.Digest
    build_deps: _containers.RepeatedCompositeFieldContainer[Artifact.Dependency]
    public_data: _remote_execution_pb2.Digest
    logs: _containers.RepeatedCompositeFieldContainer[Artifact.LogFile]
    buildtree: _remote_execution_pb2.Digest
    sources: _remote_execution_pb2.Digest
    low_diversity_meta: _remote_execution_pb2.Digest
    high_diversity_meta: _remote_execution_pb2.Digest
    strict_key: str
    buildroot: _remote_execution_pb2.Digest
    def __init__(self, version: _Optional[int] = ..., build_success: bool = ..., build_error: _Optional[str] = ..., build_error_details: _Optional[str] = ..., strong_key: _Optional[str] = ..., weak_key: _Optional[str] = ..., was_workspaced: bool = ..., files: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., build_deps: _Optional[_Iterable[_Union[Artifact.Dependency, _Mapping]]] = ..., public_data: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., logs: _Optional[_Iterable[_Union[Artifact.LogFile, _Mapping]]] = ..., buildtree: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., sources: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., low_diversity_meta: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., high_diversity_meta: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., strict_key: _Optional[str] = ..., buildroot: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ...) -> None: ...
