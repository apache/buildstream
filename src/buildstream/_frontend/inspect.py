import json
import sys
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum

from ..types import _PipelineSelection, _Scope


# Inspectable Elements as serialized to the terminal
@dataclass
class _Element:
    name: str
    description: str
    workspace: any
    key: str
    key_full: str
    state: str
    environment: dict[str, str]
    variables: dict[str, str]
    artifact: any
    dependencies: list[str]
    build_dependencies: list[str]
    runtime_dependencies: list[str]
    sources: list[dict[str, str]]


# Representation of a cache server
@dataclass
class _CacheServer:
    url: str
    instance: str

    def __init__(self, spec):
        self.url = spec.url
        self.instance = spec.instance_name


# User configuration
@dataclass
class _UserConfig:
    configuration: str
    cache_directory: str
    log_directory: str
    source_directory: str
    build_directory: str
    source_mirrors: str
    build_area: str
    strict_build_plan: bool
    cache_directory: str
    maximum_fetch_tasks: int
    maximum_build_tasks: int
    maximum_push_tasks: int
    maximum_network_retries: int
    cache_storage_service: _CacheServer | None
    # remote specs
    remote_execution_service: _CacheServer | None
    remote_storage_service: _CacheServer | None
    remote_action_cache_service: _CacheServer | None


# String representation of loaded plugins
@dataclass
class _Plugin:
    name: str
    full: str  # class str


# Configuration of a given project
@dataclass
class _ProjectConfig:
    name: str
    directory: str | None
    junction: str | None
    variables: [(str, str)]
    element_plugins: [_Plugin]
    source_plugins: [_Plugin]


# A single project loaded from the current configuration
@dataclass
class _Project:
    provenance: str
    duplicates: [str]
    declarations: [str]
    config: _ProjectConfig


# Wrapper object ecapsulating the entire output of `bst inspect`
@dataclass
class _InspectOutput:
    project: [_Project]
    # user configuration
    user_config: _UserConfig
    elements: list[_Element]


# Used to indicate the state of a given element
class _ElementState(StrEnum):
    # Cannot determine the element state
    NO_REFERENCE = "no-reference"

    # The element has failed
    FAILED = "failed"

    # The element is a junction
    JUNCTION = "junction"

    # The element is waiting
    WAITING = "waiting"

    # The element is cached
    CACHED = "cached"

    # The element needs to be loaded from a remote source
    FETCH_NEEDED = "fetch-needed"

    # The element my be built
    BUILDABLE = "buildable"


# _make_dataclass()
#
# This is a helper class for extracting values from different objects used
# across Buildstream into JSON serializable output.
#
# If keys is a list of str then each attribute is copied directly to the
# dataclass.
# If keys is a tuple of str then the first value is extracted from the object
# and renamed to the second value.
#
# The field of kwarg is mapped directly onto the dataclass. If the value is
# callable then that function is called passing the object to it.
#
# Args:
#       obj: Whichever object you are serializing
#       _cls: The dataclass you are constructing
#       keys: attributes to include directly from the obj
#       kwargs: key values passed into the dataclass
def _make_dataclass(obj, _cls, keys: list[(str, str)] | list[str], **kwargs):
    params = dict()
    for key in keys:
        name = None
        rename = None
        if isinstance(key, tuple):
            name = key[0]
            rename = key[1]
        elif isinstance(key, str):
            name = key
            rename = None
        else:
            raise Exception("BUG: Keys may only be (str, str) or str")
        value = None
        if isinstance(obj, dict):
            value = obj.get(name)
        elif isinstance(obj, object):
            try:
                value = getattr(obj, name)
            except AttributeError:
                pass
        else:
            raise Exception("BUG: obj must be a dict or object")
        if rename:
            params[rename] = value
        else:
            params[name] = value
    for key, helper in kwargs.items():
        if callable(helper):
            params[key] = helper(obj)
        else:
            params[key] = helper
    return _cls(**params)


# Recursively dump the dataclass into a serializable dictionary. Null values
# are dropped from the output.
def _dump_dataclass(_cls):
    d = dict()
    if not is_dataclass(_cls):
        raise Exception("BUG: obj must be a dataclass")
    for field in fields(_cls):
        value = getattr(_cls, field.name)
        if value is None:  # hide null values
            continue
        if is_dataclass(value):
            d[field.name] = _dump_dataclass(value)
        elif isinstance(value, list):
            items = []
            for item in value:
                if is_dataclass(item):
                    # check if it's a list of dataclasses
                    items.append(_dump_dataclass(item))
                else:
                    items.append(item)
            d[field.name] = items
        else:
            d[field.name] = value
    return d


# Inspect elements from a given Buildstream project
class Inspector:
    def __init__(self, stream, project, context):
        self.stream = stream
        self.project = project
        self.context = context

    def _read_state(self, element):
        try:
            if not element._has_all_sources_resolved():
                return _ElementState.NO_REFERENCE
            else:
                if element.get_kind() == "junction":
                    return _ElementState.JUNCTION
                elif not element._can_query_cache():
                    return _ElementState.WAITING
                elif element._cached_failure():
                    return _ElementState.FAILED
                elif element._cached_success():
                    return _ElementState.CACHED
                elif not element._can_query_source_cache():
                    return _ElementState.WAITING
                elif element._fetch_needed():
                    return _ElementState.FETCH_NEEDED
                elif element._buildable():
                    return _ElementState.BUILDABLE
                else:
                    return _ElementState.WAITING
        except BstError as e:
            # Provide context to plugin error
            e.args = ("Failed to determine state for {}: {}".format(element._get_full_name(), str(e)),)
            raise e

    def _elements(self, dependencies, with_state=False):
        for element in dependencies:

            # These operations require state and are only shown if requested
            key = None
            key_full = None
            state = None
            artifact = None

            if with_state:
                key = element._get_display_key().brief

                key_full = element._get_display_key().full

                state = self._read_state(element).value

                # BUG: Due to the assersion within .get_artifact this will
                # error but there is no other way to determine if an artifact
                # exists and we only want to show this value for informational
                # purposes.
                try:
                    _artifact = element._get_artifact()
                    if _artifact.cached():
                        artifact = {
                            "files": artifact.get_files(),
                            "digest": artifact_files._get_digest(),
                        }
                except:
                    pass

            sources = []
            for source in element.sources():
                source_infos = source.collect_source_info()

                if source_infos is not None:
                    serialized_sources = []
                    for s in source_infos:
                        serialized = s.serialize()
                        serialized_sources.append(serialized)

                    sources += serialized_sources

            yield _make_dataclass(
                element,
                _Element,
                [],
                name=lambda element: element._get_full_name(),
                description=lambda element: " ".join(element._description.splitlines()),
                workspace=lambda element: element._get_workspace(),
                variables=lambda element: dict(element._Element__variables),
                environment=lambda element: dict(element._Element__environment),
                sources=sources,
                dependencies=lambda element: [
                    dependency._get_full_name() for dependency in element._dependencies(_Scope.ALL, recurse=False)
                ],
                build_dependencies=lambda element: [
                    dependency._get_full_name() for dependency in element._dependencies(_Scope.BUILD, recurse=False)
                ],
                runtime_dependencies=lambda element: [
                    dependency._get_full_name() for dependency in element._dependencies(_Scope.RUN, recurse=False)
                ],
                key=key,
                key_full=key_full,
                state=state,
                artifact=artifact,
            )

    def _get_projects(self) -> [_Project]:
        projects = []
        for wrapper in self.project.loaded_projects():
            variables = dict()
            wrapper.project.options.printable_variables(variables)
            project_config = _make_dataclass(
                wrapper.project,
                _ProjectConfig,
                ["name", "directory"],
                variables=variables,
                junction=lambda config: None if not config.junction else config.junction._get_full_name(),
                element_plugins=lambda config: [
                    _Plugin(name=plugin[0], full=str(plugin[1])) for plugin in config.element_factory.list_plugins()
                ],
                source_plugins=lambda config: [
                    _Plugin(name=plugin[0], full=str(plugin[1])) for plugin in config.source_factory.list_plugins()
                ],
            )
            projects.append(
                _make_dataclass(
                    wrapper,
                    _Project,
                    keys=["provenance"],
                    duplicates=lambda config: (
                        [] if not hasattr(config, "duplicates") else [duplicate for duplicate in config.duplicates]
                    ),
                    declarations=lambda config: (
                        []
                        if not hasattr(config, "declarations")
                        else [declaration for declaration in config.declarations]
                    ),
                    config=project_config,
                )
            )
        return projects

    def _get_user_config(self) -> _UserConfig:

        remote_execution_service = None
        remote_storage_service = None
        remote_action_cache_service = None

        if self.context.remote_execution_specs:
            specs = self.context.remote_execution_specs
            remote_execution_service = _CacheServer(specs.exec_spec)
            storage_spec = specs.storage_spec or self.context.remote_cache_spec
            remote_storage_spec = _CacheServer(storage_spec)
            if specs.action_spec:
                remote_action_cache_service = _CacheServer(specs.action_spec)

        return _make_dataclass(
            self.context,
            _UserConfig,
            [
                ("cachedir", "cache_directory"),
                ("logdir", "log_directory"),
                ("sourcedir", "source_directory"),
                ("builddir", "build_directory"),
                ("sourcedir", "source_mirrors"),
                ("builddir", "build_area"),
                ("cachedir", "cache_directory"),
                ("sched_fetchers", "maximum_fetch_tasks"),
                ("sched_builders", "maximum_build_tasks"),
                ("sched_pushers", "maximum_push_tasks"),
                ("sched_network_retries", "maximum_network_retries"),
            ],
            strict_build_plan=lambda context: (
                "Default Configuration" if not context.config_origin else context.config_origin
            ),
            configuration=lambda context: "default" if not context.config_origin else context.config_origin,
            cache_storage_service=lambda context: (
                None if not context.remote_execution_specs else _CacheServer(context.remote_execution_specs)
            ),
            remote_execution_service=remote_execution_service,
            remote_storage_service=remote_storage_service,
            remote_action_cache_service=remote_action_cache_service,
        )

    def _get_output(self, dependencies, with_state=False) -> _InspectOutput:
        return _InspectOutput(
            project=self._get_projects(),
            user_config=self._get_user_config(),
            elements=[element for element in self._elements(dependencies, with_state=with_state)],
        )

    def dump_to_stdout(self, elements=[], selection=_PipelineSelection.NONE, with_state=False):
        if not elements:
            elements = self.project.get_default_targets()

        dependencies = self.stream.load_selection(
            elements, selection=selection, except_targets=[], need_state=with_state
        )

        if with_state:
            self.stream.query_cache(dependencies, need_state=True)

        output = self._get_output(dependencies, with_state)
        json.dump(_dump_dataclass(output), sys.stdout)
