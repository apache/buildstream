import json
import sys
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum

from .._project import ProjectConfig as _BsProjectConfig
from .._pluginfactory.pluginorigin import PluginType
from .._options import OptionPool
from ..types import _PipelineSelection, _Scope
from ..node import MappingNode


# Inspectable Elements as serialized to the terminal
@dataclass
class _Element:
    name: str
    description: str
    workspace: any
    environment: dict[str, str]
    variables: dict[str, str]
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
    description: str
    plugin_type: PluginType


# Configuration of a given project
@dataclass
class _ProjectConfig:
    name: str
    directory: str | None
    # Original configuration from the project.conf
    original: dict[str, any]
    junction: str | None
    # Interpolated options
    options: [(str, str)]
    aliases: dict[str, str]
    element_overrides: any
    source_overrides: any
    # plugin information
    plugins: [_Plugin]


# A single project loaded from the current configuration
@dataclass
class _Project:
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


def _dump_option_pool(options: OptionPool):
    opts = dict()
    return options.export_variables(opts)


def _maybe_strip_node_info(obj):
    out = dict()
    if obj and hasattr(obj, "strip_node_info"):
        return obj.strip_node_info()


# Inspect elements from a given Buildstream project
class Inspector:
    def __init__(self, stream, project, context):
        self.stream = stream
        self.project = project
        self.context = context

    def _elements(self, dependencies):
        for element in dependencies:

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
            )

    def _get_projects(self) -> [_Project]:
        projects = []
        for wrapper in self.project.loaded_projects():
            plugins = []
            plugins.extend(
                [
                    _Plugin(name=plugin[0], description=plugin[3], plugin_type=PluginType.ELEMENT.value)
                    for plugin in wrapper.project.element_factory.list_plugins()
                ]
            )
            plugins.extend(
                [
                    _Plugin(name=plugin[0], description=plugin[3], plugin_type=PluginType.SOURCE.value)
                    for plugin in wrapper.project.source_factory.list_plugins()
                ]
            )
            plugins.extend(
                [
                    _Plugin(name=plugin[0], description=plugin[3], plugin_type=PluginType.SOURCE_MIRROR.value)
                    for plugin in wrapper.project.source_factory.list_plugins()
                ]
            )

            project_config = _make_dataclass(
                wrapper.project,
                _ProjectConfig,
                ["name", "directory"],
                options=lambda project: _dump_option_pool(project.options),
                original=lambda project: _maybe_strip_node_info(project._project_conf),
                aliases=lambda project: _maybe_strip_node_info(project.config._aliases),
                source_overrides=lambda project: _maybe_strip_node_info(project.source_overrides),
                element_overrides=lambda project: _maybe_strip_node_info(project.element_overrides),
                junction=lambda project: None if not project.junction else project.junction._get_full_name(),
                plugins=plugins,
            )
            projects.append(
                _make_dataclass(
                    wrapper,
                    _Project,
                    keys=[],
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

    def _get_output(self, dependencies) -> _InspectOutput:
        return _InspectOutput(
            project=self._get_projects(),
            user_config=self._get_user_config(),
            elements=[element for element in self._elements(dependencies)],
        )

    def dump_to_stdout(self, elements=[], except_=[], selection=_PipelineSelection.NONE):
        if not elements:
            elements = self.project.get_default_targets()

        elements = [element for element in filter(lambda name: name not in except_, elements)]

        dependencies = self.stream.load_selection(elements, selection=selection, except_targets=[])

        output = self._get_output(dependencies)
        json.dump(_dump_dataclass(output), sys.stdout)
