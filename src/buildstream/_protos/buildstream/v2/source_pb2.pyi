from build.bazel.remote.execution.v2 import remote_execution_pb2 as _remote_execution_pb2
from google.api import annotations_pb2 as _annotations_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Source(_message.Message):
    __slots__ = ("version", "files")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    version: int
    files: _remote_execution_pb2.Digest
    def __init__(self, version: _Optional[int] = ..., files: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ...) -> None: ...
