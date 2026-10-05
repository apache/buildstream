import json
import sys
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum

from .._project import ProjectConfig as _BsProjectConfig, Project as _BsProject
from .._pluginfactory.pluginorigin import PluginType
from .._options import OptionPool
from .._stream import Stream
from ..types import _PipelineSelection, _Scope, _ProjectInformation
from ..node import MappingNode
from ..element import Element

from .. import _yaml
from .. import _site


class _DependencyKind(StrEnum):
    ALL = "all"
    RUNTIME = "runtime"
    BUILD = "build"


@dataclass
class _Dependency:
    name: str
    junction: str | None
    kind: _DependencyKind


# Inspectable Elements as serialized to the terminal
@dataclass
class _Element:
    name: str
    description: str
    workspace: any
    environment: dict[str, str]
    variables: dict[str, str]
    dependencies: list[_Dependency]
    sources: list[dict[str, str]]


# Representation of a cache server
@dataclass
class _CacheServer:
    url: str
    instance: str

    def __init__(self, spec):
        self.url = spec.url
        self.instance = spec.instance_name


# String representation of loaded plugins
@dataclass
class _Plugin:
    name: str
    description: str
    plugin_type: PluginType


# A single project loaded from the current configuration
@dataclass
class _Project:
    name: str
    junction: str | None
    options: [(str, str)]
    plugins: [_Plugin]
    elements: [_Element]


# Default values defined for each element within
@dataclass
class _Defaults:
    environment: dict[str, str]


# Wrapper object ecapsulating the entire output of `bst inspect`
@dataclass
class _InspectOutput:
    projects: [_Project]
    defaults: _Defaults


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
    def __init__(self, stream: Stream, project: _BsProject, context):
        self.stream = stream
        self.project = project
        self.context = context
        # Load config defaults so we can only show them once instead of
        # for each element unless they are distinct
        _default_config = _yaml.load(_site.default_project_config, shortname="projectconfig.yaml")
        self.default_environment = _default_config.get_mapping("environment").strip_node_info()

    def _get_element(self, element: Element):
        sources = []
        for source in element.sources():
            source_infos = source.collect_source_info()

            if source_infos is not None:
                serialized_sources = []
                for s in source_infos:
                    serialized = s.serialize()
                    serialized_sources.append(serialized)

                sources += serialized_sources

        junction_name = None
        project = element._get_project()
        if project:
            if hasattr(project, "junction") and project.junction:
                junction_name = project.junction.name

        named_by_kind = {
            str(_DependencyKind.ALL): {},
            str(_DependencyKind.BUILD): {},
            str(_DependencyKind.RUNTIME): {},
        }

        dependencies = []
        for dependency in element._dependencies(_Scope.ALL, recurse=True):
            named_by_kind[str(_DependencyKind.ALL)][dependency.name] = dependency
        for dependency in element._dependencies(_Scope.BUILD, recurse=True):
            named_by_kind[str(_DependencyKind.BUILD)][dependency.name] = dependency
        for dependency in element._dependencies(_Scope.RUN, recurse=True):
            named_by_kind[str(_DependencyKind.RUNTIME)][dependency.name] = dependency

        for dependency in named_by_kind[str(_DependencyKind.ALL)].values():
            dependencies.append(_Dependency(name=dependency.name, junction=junction_name, kind=_DependencyKind.ALL))

        # Filter out dependencies covered by ALL

        for name, dependency in named_by_kind[str(_DependencyKind.BUILD)].items():
            if not name in named_by_kind[str(_DependencyKind.ALL)]:
                dependencies.append(
                    _Dependency(name=dependency.name, junction=junction_name, kind=_DependencyKind.BUILD)
                )

        for name, dependency in named_by_kind[str(_DependencyKind.RUNTIME)].items():
            if not name in named_by_kind[str(_DependencyKind.ALL)]:
                dependencies.append(
                    _Dependency(name=dependency.name, junction=junction_name, kind=_DependencyKind.RUNTIME)
                )

        environment = dict()
        for key, value in element.get_environment().items():
            if key in self.default_environment and self.default_environment[key] == value:
                continue
            environment[key] = value

        return _Element(
            name=element._get_full_name(),
            description=" ".join(element._description.splitlines()),
            workspace=element._get_workspace(),
            variables=dict(element._Element__variables),
            environment=environment,
            sources=sources,
            dependencies=dependencies,
        )

    def _get_project(self, info: _ProjectInformation, project: _BsProject, elements: [Element]) -> _Project:
        plugins = []
        plugins.extend(
            [
                _Plugin(name=plugin[0], description=plugin[3], plugin_type=PluginType.ELEMENT.value)
                for plugin in project.element_factory.list_plugins()
            ]
        )
        plugins.extend(
            [
                _Plugin(name=plugin[0], description=plugin[3], plugin_type=PluginType.SOURCE.value)
                for plugin in project.source_factory.list_plugins()
            ]
        )
        plugins.extend(
            [
                _Plugin(name=plugin[0], description=plugin[3], plugin_type=PluginType.SOURCE_MIRROR.value)
                for plugin in project.source_mirror_factory.list_plugins()
            ]
        )

        options = _dump_option_pool(project.options)

        junction = None
        if hasattr(project, "junction") and project.junction:
            junction = project.junction._get_full_name()

        return _Project(
            name=project.name,
            junction=junction,
            options=options,
            plugins=plugins,
            elements=[self._get_element(element) for element in elements],
        )

    def _get_output(self, elements: [Element]) -> _InspectOutput:
        return _InspectOutput(
            projects=[
                self._get_project(wrapper, wrapper.project, elements) for wrapper in self.project.loaded_projects()
            ],
            defaults=_Defaults(environment=self.default_environment),
        )

    def dump_to_stdout(self, elements=[], except_=[], selection=_PipelineSelection.NONE):
        if not elements:
            elements = self.project.get_default_targets()

        elements = [element for element in filter(lambda name: name not in except_, elements)]

        dependencies = self.stream.load_selection(elements, selection=selection, except_targets=[])

        output = self._get_output(dependencies)
        json.dump(_dump_dataclass(output), sys.stdout)
