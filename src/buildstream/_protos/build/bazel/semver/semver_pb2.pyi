from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SemVer(_message.Message):
    __slots__ = ("major", "minor", "patch", "prerelease")
    MAJOR_FIELD_NUMBER: _ClassVar[int]
    MINOR_FIELD_NUMBER: _ClassVar[int]
    PATCH_FIELD_NUMBER: _ClassVar[int]
    PRERELEASE_FIELD_NUMBER: _ClassVar[int]
    major: int
    minor: int
    patch: int
    prerelease: str
    def __init__(self, major: _Optional[int] = ..., minor: _Optional[int] = ..., patch: _Optional[int] = ..., prerelease: _Optional[str] = ...) -> None: ...
