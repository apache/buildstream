from build.bazel.remote.execution.v2 import remote_execution_pb2 as _remote_execution_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SpeculativeActions(_message.Message):
    __slots__ = ("actions", "artifact_overlays")
    class SpeculativeAction(_message.Message):
        __slots__ = ("base_action_digest", "overlays")
        BASE_ACTION_DIGEST_FIELD_NUMBER: _ClassVar[int]
        OVERLAYS_FIELD_NUMBER: _ClassVar[int]
        base_action_digest: _remote_execution_pb2.Digest
        overlays: _containers.RepeatedCompositeFieldContainer[SpeculativeActions.Overlay]
        def __init__(self, base_action_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., overlays: _Optional[_Iterable[_Union[SpeculativeActions.Overlay, _Mapping]]] = ...) -> None: ...
    class Overlay(_message.Message):
        __slots__ = ("type", "source_element", "source_path", "target_digest", "source_action_digest")
        class OverlayType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            SOURCE: _ClassVar[SpeculativeActions.Overlay.OverlayType]
            ARTIFACT: _ClassVar[SpeculativeActions.Overlay.OverlayType]
            ACTION: _ClassVar[SpeculativeActions.Overlay.OverlayType]
        SOURCE: SpeculativeActions.Overlay.OverlayType
        ARTIFACT: SpeculativeActions.Overlay.OverlayType
        ACTION: SpeculativeActions.Overlay.OverlayType
        TYPE_FIELD_NUMBER: _ClassVar[int]
        SOURCE_ELEMENT_FIELD_NUMBER: _ClassVar[int]
        SOURCE_PATH_FIELD_NUMBER: _ClassVar[int]
        TARGET_DIGEST_FIELD_NUMBER: _ClassVar[int]
        SOURCE_ACTION_DIGEST_FIELD_NUMBER: _ClassVar[int]
        type: SpeculativeActions.Overlay.OverlayType
        source_element: str
        source_path: str
        target_digest: _remote_execution_pb2.Digest
        source_action_digest: _remote_execution_pb2.Digest
        def __init__(self, type: _Optional[_Union[SpeculativeActions.Overlay.OverlayType, str]] = ..., source_element: _Optional[str] = ..., source_path: _Optional[str] = ..., target_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ..., source_action_digest: _Optional[_Union[_remote_execution_pb2.Digest, _Mapping]] = ...) -> None: ...
    ACTIONS_FIELD_NUMBER: _ClassVar[int]
    ARTIFACT_OVERLAYS_FIELD_NUMBER: _ClassVar[int]
    actions: _containers.RepeatedCompositeFieldContainer[SpeculativeActions.SpeculativeAction]
    artifact_overlays: _containers.RepeatedCompositeFieldContainer[SpeculativeActions.Overlay]
    def __init__(self, actions: _Optional[_Iterable[_Union[SpeculativeActions.SpeculativeAction, _Mapping]]] = ..., artifact_overlays: _Optional[_Iterable[_Union[SpeculativeActions.Overlay, _Mapping]]] = ...) -> None: ...
