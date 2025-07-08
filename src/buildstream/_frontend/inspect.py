import json
import sys

from dataclasses import dataclass

from ruamel.yaml import YAML

from ..types import _Encoding, _ElementState, _PipelineSelection, _Scope

# Inspectable Elements as serialized to the terminal
@dataclass
class _InspectElement:
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

@dataclass
class _ProjectOutput:
    name: str
    directory: str

@dataclass
class _InspectOutput:
    project: _ProjectOutput
    elements: list[_InspectElement]

# Inspect elements from a given Buildstream project
class Inspector:
    def __init__(self, stream, project):
        self.stream = stream
        self.project = project

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

            name = element._get_full_name()
            description = " ".join(element._description.splitlines())
            workspace = element._get_workspace()
            variables = dict(element._Element__variables)
            environment = dict(element._Element__environment)

            sources = []
            for source in element.sources():
                source_infos = source.collect_source_info()

                if source_infos is not None:
                    serialized_sources = []
                    for s in source_infos:
                        serialized = s.serialize()
                        serialized_sources.append(serialized)

                    sources += serialized_sources

            # Show dependencies
            dependencies = [e._get_full_name() for e in element._dependencies(_Scope.ALL, recurse=False)]

            # Show build dependencies
            build_dependencies = [e._get_full_name() for e in element._dependencies(_Scope.BUILD, recurse=False)]

            # Show runtime dependencies
            runtime_dependencies = runtime_dependencies = [e._get_full_name() for e in element._dependencies(_Scope.RUN, recurse=False)]

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

            yield _InspectElement(
                name=name,
                description=description,
                workspace=workspace,
                key=key,
                key_full=key_full,
                state=state,
                environment=environment,
                variables=variables,
                artifact=artifact,
                dependencies=dependencies,
                build_dependencies=build_dependencies,
                runtime_dependencies=runtime_dependencies,
                sources=sources,
            )


    def _dump_project(self):
        # TODO: What else do we want here?
        return _ProjectOutput(name=self.project.name, directory=self.project.directory)


    def _get_output(self, dependencies, with_state=False):
        project = self._dump_project()
        elements = []
        for element in self._elements(dependencies, with_state=with_state):
            elements.append(element)
        return _InspectOutput(project=project, elements=elements)


    def _to_dict(self, dependencies, with_state=False):
        output = self._get_output(dependencies, with_state)

        def _hide_null(element):
            d = dict()
            for key, value in element.__dict__.items():
                if value:
                    d[key] = value
            return d

        return {"project": _hide_null(output.project), "elements": [_hide_null(element) for element in output.elements]}


    def dump_to_stdout(self, elements=[], selection=_PipelineSelection.NONE, with_state=False, encoding=_Encoding.JSON):
        if not elements:
            elements = self.project.get_default_targets()

        dependencies = self.stream.load_selection(
            elements, selection=selection, except_targets=[], need_state=with_state
        )

        if with_state:
            self.stream.query_cache(dependencies, need_state=True)

        if encoding == _Encoding.JSON:
            json.dump(self._to_dict(dependencies, with_state), sys.stdout)
        elif encoding == _Encoding.YAML:
            yaml = YAML()
            yaml.dump(self._to_dict(dependencies, with_state), sys.stdout)
