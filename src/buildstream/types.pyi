"""
Foundation type stubs
================

See src/buildstream/types.py

These stubs are used to replace FastEnum with Enum when doing static type checking.

Buildstream implements a custom `FastEnum`[1].
mypy only supports `enum.Enum` (and it's official variations) when it comes to doing static type checks on enums [2].
We can't subclass Enum in FastEnum to make mypy happy, because Enum doesn't allow subclassing [3].
So we end up with a bunch of `str`, `int` etc around the codebase,
instead of the appropriate Enum classes like `OverlapAction` or `_Scope` which are usually recorded separately in the doc strings.
This means we don't get proper static type checking on our Enums :( .
With stub files [4][5] we can lie to mypy about what type the Enum classes are[6],
so the type hints around the codebase are now correct be corrected.
Now we can have proper static type checking on the custom Enums, Yay!

So

```
class OverlapAction(FastEnum):
    ERROR: str
    WARNING: str
    IGNORE: str
```

gets stubbed as

```
from enum import Enum
class OverlapAction(Enum):
    ERROR: str
    WARNING: str
    IGNORE: str
```

[1] src/buildstream/types.py#L32
[2] https://mypy.readthedocs.io/en/stable/literal_types.html#enums
[3] https://docs.python.org/3/howto/enum.html#restricted-enum-subclassing
[4] https://typing.python.org/en/latest/guides/writing_stubs.html
[5] https://mypy.readthedocs.io/en/stable/stubgen.html
[6] https://github.com/python/mypy/issues/3217

"""

from ._types import MetaFastEnum as MetaFastEnum
from .node import MappingNode as MappingNode, SequenceNode as SequenceNode
from _typeshed import Incomplete
from typing import Any
from enum import Enum

class FastEnum(metaclass=MetaFastEnum):
    """
    A reimplementation of a subset of the `Enum` functionality, which is far quicker than `Enum`.

    :class:`enum.Enum` attributes accesses can be really slow, and slow down the execution noticeably.
    This reimplementation doesn't suffer the same problems, but also does not reimplement everything.

    For mypy Enum static type checking support, all FastEnum should be stubbed as inheriting from enum.Enum.
    Use `stubgen src/buildstream/types.py --include-docstrings` to generate the stubs, add `from enum import Enum` and replace all `(FastEnum)` with `(Enum)`
    """

    name: Incomplete
    value: Incomplete
    @classmethod
    def values(cls):
        """Get all the possible values for the enum.

        Returns:
            list: the list of all possible values for the enum
        """

    def __new__(cls, value): ...
    def __eq__(self, other): ...
    def __ne__(self, other): ...
    def __hash__(self): ...
    def __reduce__(self): ...

class CoreWarnings:
    """CoreWarnings()

    Some common warnings which are raised by core functionalities within BuildStream are found in this class.
    """

    OVERLAPS: str
    UNSTAGED_FILES: str
    REF_NOT_IN_TRACK: str
    UNALIASED_URL: str
    UNAVAILABLE_SOURCE_INFO: str

class OverlapAction(Enum):
    """OverlapAction()

    Defines what action to take when files staged into the sandbox overlap.

    .. note::

       This only dictates what happens when functions such as
       :func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>` and
       :func:`Element.stage_dependency_artifacts() <buildstream.element.Element.stage_dependency_artifacts>`
       are called multiple times in an Element's :func:`Element.stage() <buildstream.element.Element.stage>`
       implementation, and the files staged from one function call result in overlapping files staged
       from previous invocations.

       If multiple staged elements overlap eachother within a single call to
       :func:`Element.stage_dependency_artifacts() <buildstream.element.Element.stage_dependency_artifacts>`,
       then the :ref:`overlap whitelist <public_overlap_whitelist>` will be ovserved, and warnings will
       be issued for overlapping files, which will be fatal warnings if
       :attr:`CoreWarnings.OVERLAPS <buildstream.types.CoreWarnings.OVERLAPS>` is specified
       as a :ref:`fatal warning <configurable_warnings>`.
    """

    ERROR: str
    WARNING: str
    IGNORE: str

class _Scope(Enum):
    ALL: int
    BUILD: int
    RUN: int
    NONE: int

class _KeyStrength(Enum):
    STRONG: int
    WEAK: int

class _DisplayKey:
    full: str
    brief: str
    strict: bool
    def __init__(self, full: str, brief: str, strict: bool) -> None: ...

class _SchedulerErrorAction(Enum):
    CONTINUE: str
    QUIT: str
    TERMINATE: str

class _CacheBuildTrees(Enum):
    ALWAYS: str
    AUTO: str
    NEVER: str

class _SourceUriPolicy(Enum):
    ALL: str
    ALIASES: str
    MIRRORS: str
    USER: str

class _PipelineSelection(Enum):
    NONE: str
    REDIRECT: str
    ALL: str
    BUILD: str
    RUN: str

class _ProjectInformation:
    project: Incomplete
    provenance: Incomplete
    duplicates: Incomplete
    internal: Incomplete
    def __init__(self, project, provenance_node, duplicates, internal) -> None: ...

class _HostMount:
    path: str
    host_path: str
    optional: bool
    def __init__(self, path: str, host_path: str | None = None, optional: bool = False) -> None: ...

class _SourceMirror:
    name: str
    aliases: dict[str, list[str]]
    def __init__(self, name: str, aliases: dict[str, list[str]]) -> None: ...
    @classmethod
    def new_from_node(cls, node: MappingNode) -> _SourceMirror: ...

SourceRef = None | int | str | list[Any] | dict[str, Any]
