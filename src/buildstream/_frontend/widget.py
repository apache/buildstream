#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
import datetime
import os
from contextlib import ExitStack
from mmap import mmap
import re
import textwrap
import click

from .profile import Profile
from ..types import _Scope
from .. import _yaml
from .. import __version__ as bst_version
from .. import FileType
from .._exceptions import BstError, ImplError
from .._message import MessageType
from .._artifactelement import ArtifactElement

# These messages are printed a bit differently
ERROR_MESSAGES = [MessageType.FAIL, MessageType.ERROR, MessageType.BUG]


class FormattingError(Exception):
    pass


# Widget()
#
# Args:
#    content_profile (Profile): The profile to use for rendering content
#    format_profile (Profile): The profile to use for rendering formatting
#
# An abstract class for printing output columns in our text UI.
#
class Widget:
    def __init__(self, context, content_profile, format_profile):

        # The context
        self.context = context

        # The content profile
        self.content_profile = content_profile

        # The formatting profile
        self.format_profile = format_profile

    # render()
    #
    # Renders a string to be printed in the UI
    #
    # Args:
    #    message (Message): A message to print
    #
    # Returns:
    #    (str): The string this widget prints for the given message
    #
    def render(self, message):
        raise ImplError("{} does not implement render()".format(type(self).__name__))


# Used to add fixed text between columns
class FixedText(Widget):
    def __init__(self, context, text, content_profile, format_profile):
        super().__init__(context, content_profile, format_profile)
        self.text = text

    def render(self, message):
        return self.format_profile.fmt(self.text)


# Used to add the wallclock time this message was created at
class WallclockTime(Widget):
    def __init__(self, context, content_profile, format_profile, output_format=False):
        self._output_format = output_format
        super().__init__(context, content_profile, format_profile)

    def render(self, message):

        fields = [
            self.content_profile.fmt("{:02d}".format(x))
            for x in [
                message.creation_time.hour,
                message.creation_time.minute,
                message.creation_time.second,
            ]
        ]
        text = self.format_profile.fmt(":").join(fields)

        if self._output_format == "us":
            text += self.content_profile.fmt(".{:06d}".format(message.creation_time.microsecond))

        return text


# A widget for rendering the debugging column
class Debug(Widget):
    def render(self, message):
        element_name = "n/a" if message.element_name is None else message.element_name

        text = self.format_profile.fmt("pid:")
        text += self.content_profile.fmt("{: <5}".format(message.pid))
        text += self.format_profile.fmt("element name:")
        text += self.content_profile.fmt("{: <30}".format(element_name))

        return text


# A widget for rendering the time codes
class TimeCode(Widget):
    def __init__(self, context, content_profile, format_profile, microseconds=False):
        self._microseconds = microseconds
        super().__init__(context, content_profile, format_profile)

    def render(self, message):
        return self.render_time(message.elapsed)

    def render_time(self, elapsed):
        if elapsed is None:
            fields = [self.content_profile.fmt("--") for i in range(3)]
        else:
            hours, remainder = divmod(int(elapsed.total_seconds()), 60 * 60)
            minutes, seconds = divmod(remainder, 60)
            fields = [self.content_profile.fmt("{0:02d}".format(field)) for field in [hours, minutes, seconds]]

        text = self.format_profile.fmt(":").join(fields)

        if self._microseconds:
            if elapsed is not None:
                text += self.content_profile.fmt(".{0:06d}".format(elapsed.microseconds))
            else:
                text += self.content_profile.fmt(".------")
        return text


# A widget for rendering the MessageType
class TypeName(Widget):

    _action_colors = {
        MessageType.DEBUG: "cyan",
        MessageType.STATUS: "cyan",
        MessageType.INFO: "magenta",
        MessageType.WARN: "yellow",
        MessageType.START: "blue",
        MessageType.SUCCESS: "green",
        MessageType.FAIL: "red",
        MessageType.SKIPPED: "yellow",
        MessageType.ERROR: "red",
        MessageType.BUG: "red",
    }

    def render(self, message):
        return self.content_profile.fmt(
            "{: <7}".format(message.message_type.upper()),
            bold=True,
            dim=True,
            fg=self._action_colors[message.message_type],
        )


# A widget for displaying the Element name
class ElementName(Widget):
    def render(self, message):
        action_name = message.action_name
        element_name = message.task_element_name or message.element_name

        if element_name is not None:
            name = "{: <30}".format(element_name)
        else:
            name = "core activity"
            name = "{: <30}".format(name)

        if not action_name:
            action_name = "Main"

        return (
            self.content_profile.fmt("{: >8}".format(action_name.lower()))
            + self.format_profile.fmt(":")
            + self.content_profile.fmt(name)
        )


# A widget for displaying the primary message text
class MessageText(Widget):
    def render(self, message):
        return message.message


# A widget for formatting the element cache key
class CacheKey(Widget):
    def __init__(self, context, content_profile, format_profile, err_profile):
        super().__init__(context, content_profile, format_profile)

        self._err_profile = err_profile
        self._key_length = context.log_key_length

    def render(self, message):

        if not self._key_length:
            return ""

        if message.element_name is None:
            return " " * self._key_length

        dim = False
        key = " " * self._key_length
        element_key = message.task_element_key or message.element_key
        if element_key:
            key = element_key.brief
            dim = not element_key.strict

        if message.message_type in ERROR_MESSAGES:
            text = self._err_profile.fmt(key)
        else:
            text = self.content_profile.fmt(key, dim=dim)

        return text


# A widget for formatting the log file
class LogFile(Widget):
    def __init__(self, context, content_profile, format_profile, err_profile):
        super().__init__(context, content_profile, format_profile)

        self._err_profile = err_profile
        self._logdir = context.logdir

    def render(self, message):
        return self.render_abbrev(message)

    def render_abbrev(self, message, abbrev=True):
        if message.logfile and message.scheduler:
            logfile = message.logfile

            if abbrev and self._logdir != "" and logfile.startswith(self._logdir):
                logfile = logfile[len(self._logdir) :]
                logfile = logfile.lstrip(os.sep)

            if message.message_type in ERROR_MESSAGES:
                text = self._err_profile.fmt(logfile)
            else:
                text = self.content_profile.fmt(logfile, dim=True)
        else:
            text = ""

        return text


# START and SUCCESS messages are expected to have no useful
# information in the message text, so we display the logfile name for
# these messages, and the message text for other types.
#
class MessageOrLogFile(Widget):
    def __init__(self, context, content_profile, format_profile, err_profile):
        super().__init__(context, content_profile, format_profile)
        self._message_widget = MessageText(context, content_profile, format_profile)
        self._logfile_widget = LogFile(context, content_profile, format_profile, err_profile)

    def render(self, message):
        # Show the log file only in the main start/success messages
        if message.logfile and message.scheduler and message.message_type in [MessageType.START, MessageType.SUCCESS]:
            text = self._logfile_widget.render(message)
        else:
            text = self._message_widget.render(message)
        return text


# LogLine
#
# A widget for formatting a log line
#
# Args:
#    context (Context): The Context
#    state (State): The state data from the Core
#    content_profile (Profile): Formatting profile for content text
#    format_profile (Profile): Formatting profile for formatting text
#    success_profile (Profile): Formatting profile for success text
#    error_profile (Profile): Formatting profile for error text
#    detail_profile (Profile): Formatting profile for detail text
#    indent (int): Number of spaces to use for general indentation
#
class LogLine(Widget):
    def __init__(
        self, context, state, content_profile, format_profile, success_profile, err_profile, detail_profile, indent=4
    ):
        super().__init__(context, content_profile, format_profile)

        self._columns = []
        self._failure_messages = {}
        self._success_profile = success_profile
        self._err_profile = err_profile
        self._detail_profile = detail_profile
        self._indent = " " * indent
        self._log_lines = context.log_error_lines
        self._message_lines = context.log_message_lines
        self._resolved_keys = None
        self._state = state

        self._logfile_widget = LogFile(context, content_profile, format_profile, err_profile)

        if context.log_debug:
            self._columns.extend([Debug(context, content_profile, format_profile)])

        self.logfile_variable_names = {
            "elapsed": TimeCode(context, content_profile, format_profile, microseconds=False),
            "elapsed-us": TimeCode(context, content_profile, format_profile, microseconds=True),
            "wallclock": WallclockTime(context, content_profile, format_profile),
            "wallclock-us": WallclockTime(context, content_profile, format_profile, output_format="us"),
            "key": CacheKey(context, content_profile, format_profile, err_profile),
            "element": ElementName(context, content_profile, format_profile),
            "action": TypeName(context, content_profile, format_profile),
            "message": MessageOrLogFile(context, content_profile, format_profile, err_profile),
        }
        logfile_tokens = self._parse_logfile_format(context.log_message_format, content_profile, format_profile)
        self._columns.extend(logfile_tokens)

    # show_pipeline()
    #
    # Display a list of elements in the specified format.
    #
    # The formatting string is the one currently documented in `bst show`, this
    # is used in pipeline session headings and also to implement `bst show`.
    #
    # Args:
    #    dependencies (list of Element): A list of Element objects
    #    format_: A formatting string, as specified by `bst show`
    #
    # Returns:
    #    (str): The formatted list of elements
    #
    def show_pipeline(self, dependencies, format_):
        report = ""
        p = Profile()

        for element in dependencies:
            line = format_

            key = element._get_display_key()
            dim_keys = not key.strict

            # Guarantee that description is reported on a single line.
            description = " ".join(element._description.splitlines())

            line = p.fmt_subst(line, "name", element._get_full_name(), fg="blue", bold=True)
            line = p.fmt_subst(line, "kind", element.get_kind(), fg="cyan")
            line = p.fmt_subst(line, "key", key.brief, fg="yellow", dim=dim_keys)
            line = p.fmt_subst(line, "full-key", key.full, fg="yellow", dim=dim_keys)
            line = p.fmt_subst(line, "description", description, fg="yellow", dim=dim_keys)

            try:
                if not element._has_all_sources_resolved():
                    line = p.fmt_subst(line, "state", "no reference", fg="red")
                else:
                    if element.get_kind() == "junction":
                        line = p.fmt_subst(line, "state", "junction", fg="magenta")
                    elif not element._can_query_cache():
                        line = p.fmt_subst(line, "state", "waiting", fg="blue")
                    elif element._cached_failure():
                        line = p.fmt_subst(line, "state", "failed", fg="red")
                    elif element._cached_success():
                        line = p.fmt_subst(line, "state", "cached", fg="magenta")
                    elif not element._can_query_source_cache():
                        line = p.fmt_subst(line, "state", "waiting", fg="blue")
                    elif element._fetch_needed():
                        line = p.fmt_subst(line, "state", "fetch needed", fg="red")
                    elif element._buildable():
                        line = p.fmt_subst(line, "state", "buildable", fg="green")
                    else:
                        line = p.fmt_subst(line, "state", "waiting", fg="blue")
            except BstError as e:
                # Provide context to plugin error
                e.args = ("Failed to determine state for {}: {}".format(element._get_full_name(), str(e)),)
                raise e

            # Element configuration
            if "%{config" in format_:
                line = p.fmt_subst(
                    line,
                    "config",
                    _yaml.roundtrip_dump_string(element._Element__config),
                )

            # Variables
            if "%{vars" in format_:
                variables = dict(element._Element__variables)
                line = p.fmt_subst(line, "vars", _yaml.roundtrip_dump_string(variables))

            # Environment
            if "%{env" in format_:
                environment = element._Element__environment
                line = p.fmt_subst(line, "env", _yaml.roundtrip_dump_string(environment))

            # Public
            if "%{public" in format_:
                public = element._Element__public
                line = p.fmt_subst(line, "public", _yaml.roundtrip_dump_string(public))

            # Workspaced
            if "%{workspaced" in format_:
                line = p.fmt_subst(line, "workspaced", "(workspaced)" if element._get_workspace() else "", fg="yellow")

            # Workspace-dirs
            if "%{workspace-dirs" in format_:
                workspace = element._get_workspace()
                if workspace is not None:
                    path = workspace.get_absolute_path()
                    if path.startswith("~/"):
                        path = os.path.join(os.getenv("HOME", "/root"), path[2:])
                    line = p.fmt_subst(line, "workspace-dirs", "Workspace: {}".format(path))
                else:
                    line = p.fmt_subst(line, "workspace-dirs", "")

            # Dependencies
            if "%{deps" in format_:
                deps = [e._get_full_name() for e in element._dependencies(_Scope.ALL, recurse=False)]
                line = p.fmt_subst(line, "deps", _yaml.roundtrip_dump_string(deps).rstrip("\n"))

            # Build Dependencies
            if "%{build-deps" in format_:
                build_deps = [e._get_full_name() for e in element._dependencies(_Scope.BUILD, recurse=False)]
                line = p.fmt_subst(line, "build-deps", _yaml.roundtrip_dump_string(build_deps).rstrip("\n"))

            # Runtime Dependencies
            if "%{runtime-deps" in format_:
                runtime_deps = [e._get_full_name() for e in element._dependencies(_Scope.RUN, recurse=False)]
                line = p.fmt_subst(line, "runtime-deps", _yaml.roundtrip_dump_string(runtime_deps).rstrip("\n"))

            # Source Information
            if "%{source-info" in format_:

                # Get all the SourceInfo objects
                #
                all_source_infos = []
                for source in element.sources():
                    source_infos = source.collect_source_info()

                    if source_infos is not None:
                        serialized_sources = []
                        for s in source_infos:
                            serialized = s.serialize()
                            serialized_sources.append(serialized)

                        all_source_infos += serialized_sources

                # Dump the SourceInfo provenance objects in yaml format
                line = p.fmt_subst(line, "source-info", _yaml.roundtrip_dump_string(all_source_infos))

            # Artifact CAS Digest
            if "%{artifact-cas-digest" in format_:
                artifact = element._get_artifact()
                if artifact.cached():
                    artifact_files = artifact.get_files()
                    # We call the private CasBasedDirectory._get_digest() for
                    # the moment, we should make it public on Directory.
                    artifact_digest = artifact_files._get_digest()
                    formated_artifact_digest = "{}/{}".format(artifact_digest.hash, artifact_digest.size_bytes)
                    line = p.fmt_subst(line, "artifact-cas-digest", formated_artifact_digest)
                else:
                    line = p.fmt_subst(line, "artifact-cas-digest", "")
                    element.warn("Cannot obtain CAS digest because artifact is not cached")

            report += line + "\n"

        return report.rstrip("\n")

    # print_heading()
    #
    # A message to be printed at program startup, indicating
    # some things about user configuration and BuildStream version
    # and so on.
    #
    # Args:
    #    toplevel_project (Project): The toplevel project we were invoked from, or None
    #    stream (Stream): The stream
    #    log_file (file): An optional file handle for additional logging
    #
    def print_heading(self, toplevel_project, stream, *, log_file):
        context = self.context
        starttime = datetime.datetime.now()
        text = ""

        def format_spec(spec):
            if spec.instance_name:
                return "{} (instance: {})".format(spec.url, spec.instance_name)
            return spec.url

        self._resolved_keys = {element: element._get_cache_key() for element in stream.session_elements}

        # Main invocation context
        text += "\n"
        text += self.content_profile.fmt("BuildStream Version {}\n".format(bst_version), bold=True)
        values = {}
        values["Session Start"] = starttime.strftime("%A, %d-%m-%Y at %H:%M:%S")
        if toplevel_project:
            values["Project"] = "{} ({})".format(toplevel_project.name, toplevel_project.directory)
        values["Targets"] = ", ".join([t.name for t in stream.targets])
        text += self._format_values(values)

        # User configurations
        text += "\n"
        text += self.content_profile.fmt("User Configuration\n", bold=True)
        values = {}
        values["Configuration File"] = "Default Configuration" if not context.config_origin else context.config_origin
        values["Cache Directory"] = context.cachedir
        values["Log Files"] = context.logdir
        values["Source Mirrors"] = context.sourcedir
        values["Build Area"] = context.builddir
        values["Strict Build Plan"] = "Yes" if context.get_strict() else "No"
        values["Maximum Fetch Tasks"] = context.sched_fetchers
        values["Maximum Build Tasks"] = context.sched_builders
        values["Maximum Push Tasks"] = context.sched_pushers
        values["Maximum Network Retries"] = context.sched_network_retries

        if context.remote_cache_spec:
            values["Cache Storage Service"] = format_spec(context.remote_cache_spec)

        text += self._format_values(values)

        if context.remote_execution_specs:
            specs = context.remote_execution_specs

            text += "\n"
            text += self.content_profile.fmt("Remote Execution Configuration\n", bold=True)
            values = {}
            if specs.exec_spec:
                values["Execution Service"] = format_spec(specs.exec_spec)
            re_storage_spec = specs.storage_spec or context.remote_cache_spec
            values["Storage Service"] = format_spec(re_storage_spec)
            if specs.action_spec:
                values["Action Cache Service"] = format_spec(specs.action_spec)
            text += self._format_values(values)

        # Print information about each loaded project
        #
        text += "\n"
        if toplevel_project:
            loaded_projects = toplevel_project.loaded_projects()
        else:
            loaded_projects = []

        for project_info in loaded_projects:
            project = project_info.project

            # Project title line
            text += (
                self.content_profile.fmt("Project", bold=True)
                + self.format_profile.fmt(": ", bold=True)
                + self.content_profile.fmt(project.name, bold=True)
            )
            text += "\n"

            # Details on how the project was loaded
            #
            values = {}
            if project.junction:
                values["Junction path"] = project_info.project.junction._get_full_name()
            if project_info.provenance:
                values["Loaded by"] = str(project_info.provenance)
            text += self._format_values(values)

            # Print out duplicate declarations
            if project_info.duplicates:
                text += self.format_profile.fmt("{}Declared duplicate by:\n".format(self._indent))
                for duplicate in project_info.duplicates:
                    text += self.content_profile.fmt("{}{}\n".format(self._indent * 2, duplicate))

            # Print out internal declarations
            if project_info.internal:
                text += self.format_profile.fmt("{}Declared internal by:\n".format(self._indent))
                for internal in project_info.internal:
                    text += self.content_profile.fmt("{}{}\n".format(self._indent * 2, internal))

            text += "\n"

            # Project Options
            values = {}
            project.options.printable_variables(values)
            if values:
                text += self.format_profile.fmt("{}Project Options\n".format(self._indent))
                text += self._format_values(values, indent=2)
                text += "\n"

            # Plugins
            text += self._format_plugins(
                {p: d for p, _, _, d in project.element_factory.list_plugins()},
                {p: d for p, _, _, d in project.source_factory.list_plugins()},
            )

            # Artifact cache servers
            specs = context.project_artifact_cache_specs.get(project.name)
            if specs:
                text += self.format_profile.fmt("{}Artifact cache servers\n".format(self._indent))
                text += self._format_list(specs, indent=2)
                text += "\n"

            # Source cache servers
            specs = context.project_source_cache_specs.get(project.name)
            if specs:
                text += self.format_profile.fmt("{}Source cache servers\n".format(self._indent))
                text += self._format_list(specs, indent=2)
                text += "\n"

        # Pipeline state
        text += self.content_profile.fmt("Pipeline\n", bold=True)
        text += self.show_pipeline(stream.total_elements, context.log_element_format)
        text += "\n"

        # Separator line before following output
        text += self.format_profile.fmt("=" * 79 + "\n")

        click.echo(text, nl=False, err=True)
        if log_file:
            click.echo(text, file=log_file, color=False, nl=False)

    # print_summary()
    #
    # Print a summary of activities at the end of a session
    #
    # Args:
    #    stream (Stream): The Stream
    #    log_file (file): An optional file handle for additional logging
    #
    def print_summary(self, stream, log_file):

        # Early silent return if there are no queues, can happen
        # only in the case that the stream early returned due to
        # an inconsistent pipeline state.
        if not self._state.task_groups:
            return

        text = ""

        assert self._resolved_keys is not None
        elements = sorted(e for (e, k) in self._resolved_keys.items() if k != e._get_cache_key())
        if elements:
            text += self.content_profile.fmt("Resolved key Summary\n", bold=True)
            text += self.show_pipeline(elements, self.context.log_element_format)
            text += "\n\n"

        if self._failure_messages:
            values = {}

            for element_name, message in sorted(self._failure_messages.items()):
                for group in self._state.task_groups.values():
                    # Exclude the failure messages if the job didn't ultimately fail
                    # (e.g. succeeded on retry)
                    if element_name in group.failed_tasks:
                        values[element_name] = self._render(message)

            if values:
                text += self.content_profile.fmt("Failure Summary\n", bold=True)
                text += self._format_values(values, style_value=False)

        text += self.content_profile.fmt("Pipeline Summary\n", bold=True)
        values = {}

        values["Total"] = self.content_profile.fmt(str(len(stream.total_elements)))
        values["Session"] = self.content_profile.fmt(str(len(stream.session_elements)))

        processed_maxlen = 1
        skipped_maxlen = 1
        failed_maxlen = 1
        for group in self._state.task_groups.values():
            processed_maxlen = max(len(str(group.processed_tasks)), processed_maxlen)
            skipped_maxlen = max(len(str(group.skipped_tasks)), skipped_maxlen)
            failed_maxlen = max(len(str(len(group.failed_tasks))), failed_maxlen)

        for group in self._state.task_groups.values():
            processed = str(group.processed_tasks)
            skipped = str(group.skipped_tasks)
            failed = str(len(group.failed_tasks))

            processed_align = " " * (processed_maxlen - len(processed))
            skipped_align = " " * (skipped_maxlen - len(skipped))
            failed_align = " " * (failed_maxlen - len(failed))

            status_text = (
                self.content_profile.fmt("processed ")
                + self._success_profile.fmt(processed)
                + self.format_profile.fmt(", ")
                + processed_align
            )

            status_text += (
                self.content_profile.fmt("skipped ")
                + self.content_profile.fmt(skipped)
                + self.format_profile.fmt(", ")
                + skipped_align
            )

            status_text += self.content_profile.fmt("failed ") + self._err_profile.fmt(failed) + " " + failed_align
            values["{} Queue".format(group.name)] = status_text

        text += self._format_values(values, style_value=False)

        click.echo(text, nl=False, err=True)
        if log_file:
            click.echo(text, file=log_file, color=False, nl=False)

    ###################################################
    #             Widget Abstract Methods             #
    ###################################################

    def render(self, message):

        # Track logfiles for later use
        element_name = message.element_name
        if message.message_type in ERROR_MESSAGES and element_name is not None:
            self._failure_messages[element_name] = message

        return self._render(message)

    ###################################################
    #                 Private Methods                 #
    ###################################################
    def _parse_logfile_format(self, format_string, content_profile, format_profile):
        logfile_tokens = []
        while format_string:
            if format_string.startswith("%%"):
                logfile_tokens.append(FixedText(self.context, "%", content_profile, format_profile))
                format_string = format_string[2:]
                continue
            m = re.search(r"^%\{([^\}]+)\}", format_string)
            if m is not None:
                variable = m.group(1)
                format_string = format_string[m.end(0) :]
                if variable not in self.logfile_variable_names:
                    raise FormattingError("'{0}' is not a valid log variable name.".format(variable))
                logfile_tokens.append(self.logfile_variable_names[variable])
            else:
                m = re.search("^[^%]+", format_string)
                if m is not None:
                    text = FixedText(self.context, m.group(0), content_profile, format_profile)
                    format_string = format_string[m.end(0) :]
                    logfile_tokens.append(text)
                else:
                    # No idea what to do now
                    raise FormattingError(
                        "'{0}' could not be parsed into a valid logging format.".format(format_string)
                    )
        return logfile_tokens

    def _render(self, message):

        # Render the column widgets first
        text = ""
        for widget in self._columns:
            text += widget.render(message)

        text += "\n"

        extra_nl = False

        # Now add some custom things
        if message.detail:

            # Identify frontend messages, we never abbreviate these
            frontend_message = not message.element_name

            # Split and truncate message detail down to message_lines lines
            lines = message.detail.splitlines(True)

            n_lines = len(lines)
            abbrev = False
            if message.message_type not in ERROR_MESSAGES and not frontend_message and n_lines > self._message_lines:
                lines = lines[0 : self._message_lines]
                if self._message_lines > 0:
                    abbrev = True
            else:
                lines[n_lines - 1] = lines[n_lines - 1].rstrip("\n")

            detail = self._indent + self._indent.join(lines)

            text += "\n"
            if message.message_type in ERROR_MESSAGES:
                text += self._err_profile.fmt(detail, bold=True)
            else:
                text += self._detail_profile.fmt(detail)

            if abbrev:
                text += self._indent + self.content_profile.fmt(
                    "Message contains {} additional lines".format(n_lines - self._message_lines), dim=True
                )
            text += "\n"

            extra_nl = True

        if message.scheduler and message.message_type == MessageType.FAIL:
            text += "\n"

            if self.context is not None and not self.context.log_verbose:
                text += self._indent + self._err_profile.fmt("Log file: ")
                text += self._indent + self._logfile_widget.render(message) + "\n"
            elif self._log_lines > 0:
                text += (
                    self._indent
                    + self._err_profile.fmt("Printing the last {} lines from log file:".format(self._log_lines))
                    + "\n"
                )
                text += self._indent + self._logfile_widget.render_abbrev(message, abbrev=False) + "\n"
                text += self._indent + self._err_profile.fmt("=" * 70) + "\n"

                log_content = self._read_last_lines(message.logfile)
                log_content = textwrap.indent(log_content, self._indent)
                text += self._detail_profile.fmt(log_content)
                text += "\n"
                text += self._indent + self._err_profile.fmt("=" * 70) + "\n"
            extra_nl = True

        if extra_nl:
            text += "\n"

        return text

    def _read_last_lines(self, logfile):
        with ExitStack() as stack:
            # mmap handles low-level memory details, allowing for
            # faster searches
            f = stack.enter_context(open(logfile, "r+", encoding="utf-8"))
            log = stack.enter_context(mmap(f.fileno(), os.path.getsize(f.name)))

            count = 0
            end = log.size() - 1

            while count < self._log_lines and end >= 0:
                location = log.rfind(b"\n", 0, end)
                count += 1

                # If location is -1 (none found), this will print the
                # first character because of the later +1
                end = location

            # end+1 is correct whether or not a newline was found at
            # that location. If end is -1 (seek before beginning of file)
            # then we get the first characther. If end is a newline position,
            # we discard it and only want to print the beginning of the next
            # line.
            lines = log[(end + 1) :].splitlines()
            return "\n".join([line.decode("utf-8") for line in lines]).rstrip()

    # _format_plugins()
    #
    # Formats the plugins loaded by a project
    #
    # Args:
    #    element_plugins (dict): Dict of element plugin kind and display string tuples
    #    source_plugins (dict): Dict of source plugin kind and display string tuples
    #
    # Returns:
    #    (str): The formatted text
    #
    def _format_plugins(self, element_plugins, source_plugins):
        text = ""
        if element_plugins:
            text += self.format_profile.fmt("{}Element Plugins\n".format(self._indent))
            text += self._format_values(element_plugins, style_key=True, indent=2)
            text += "\n"
        if source_plugins:
            text += self.format_profile.fmt("{}Source Plugins\n".format(self._indent))
            text += self._format_values(source_plugins, style_key=True, indent=2)
            text += "\n"

        return text

    # _format_values()
    #
    # Formats an indented dictionary of titles / values, ensuring
    # the values are aligned.
    #
    # Args:
    #    values (dict): A dictionary
    #    style_key (bool): Whether to use the content profile for the keys
    #    style_value (bool): Whether to use the content profile for the values
    #    indent (number): Number of initial indentation levels
    #
    # Returns:
    #    (str): The formatted values
    #
    def _format_values(self, values, *, style_key=False, style_value=True, indent=1):
        text = ""
        max_key_len = 0
        for key, value in values.items():
            max_key_len = max(len(key), max_key_len)

        for key, value in values.items():

            key = str(key)
            text += self._indent * indent
            if style_key:
                text += self.content_profile.fmt(key)
            else:
                text += self.format_profile.fmt(key)
            text += self.format_profile.fmt(":")

            # Special case for values containing newlines
            if isinstance(value, str) and "\n" in value:
                text += "\n"
                text += textwrap.indent(value, self._indent * indent)
                continue

            # Alignment spacing
            text += " {}".format(" " * (max_key_len - len(key)))

            # Print the value
            if style_value:
                text += self.content_profile.fmt(str(value))
            else:
                text += str(value)
            text += "\n"

        return text

    # _format_list()
    #
    # Formats an indented list of values, ensuring the values have bullets.
    #
    # Args:
    #    values (list): A list of values to format as strings (or strings)
    #    indent (number): Number of initial indentation levels (must be >= 1)
    #
    # Returns:
    #    (str): The formatted values
    #
    def _format_list(self, values, *, indent=1):
        text = ""

        # We need at least 2 leading spaces inside the indentation in order
        # to print bullets.
        assert indent >= 1

        # Indent string in case of multiline values
        indent_string = self._indent * indent

        # Prepare the indented bullet right away
        indent_bullet = self.format_profile.fmt(indent_string[:-2] + "* ")

        for value in values:
            value = str(value)

            # In case of newlines, replace each newline in the value with a trailing
            # indent and strip the result.
            value = value.replace("\n", "\n" + indent_string)
            value = value.strip()

            # Append the bullet
            text += indent_bullet

            # Append the value
            text += self.content_profile.fmt(value)
            text += "\n"

        return text

    # pretty_print_element_contents()
    #
    # Formats a dictionary of elements and their contents in a human readable way
    #
    # Args:
    #    values (Dict[str, Directory]): A dictionary
    #    style_value (bool): Whether to use the content profile for the values
    #    list_long (bool): whether to display verbose information about files
    #
    # Returns:
    #    (str): The formatted element contents
    #
    def pretty_print_element_contents(self, values, long_=False, style_value=True):
        text = ""

        for element_name, directory in values.items():

            text += self.format_profile.fmt("  {}:".format(element_name))

            rendered_files = []
            for filename in directory.list_relative_paths():
                filestat = directory.stat(filename)
                rendered_files.append(self._get_filestats(directory, filename, filestat, list_long=long_))

            value_list = "\n\t" + "\n\t".join(rendered_files)

            if not rendered_files:
                message = "\n\tThis element has no associated artifacts"
                if style_value:
                    text += self.content_profile.fmt(message)
                else:
                    text += message
            elif style_value:
                text += self.content_profile.fmt(value_list)
            else:
                text += value_list
            text += "\n"

        return text

    # show_state_of_artifacts()
    #
    # Show the cached status of artifacts
    #
    # Example output:
    #
    #    "cached      foo.bst"      <- If cached locally
    #    "failed      foo.bst"      <- If cached locally as a failure
    #    "available   foo.bst"      <- If available to download from a remote
    #    "not cached  foo.bst"      <- If not cached/available remotely.
    #
    # Note that artifact names may also be displayed here.
    #
    # Args:
    #    targets (list [Element]): Elements (or ArtifactElements) we wish to show the
    #                              cached status of
    #
    def show_state_of_artifacts(self, targets):
        report = ""
        p = Profile()
        for element in targets:

            #
            # Here we selectively show the element name or artifact name
            # depending on whether we were asked about an artifact or an element.
            #
            if isinstance(element, ArtifactElement):
                element_name = element.get_artifact_name()
            else:
                element_name = element._get_full_name()

            line = "%{state: >12} %{name}"
            line = p.fmt_subst(line, "name", element_name, fg="yellow")

            if element._cached_success():
                line = p.fmt_subst(line, "state", "cached", fg="magenta")
            elif element._cached():
                line = p.fmt_subst(line, "state", "failed", fg="red")
            elif element._cached_remotely():
                line = p.fmt_subst(line, "state", "available", fg="green")
            else:
                line = p.fmt_subst(line, "state", "not cached", fg="bright_red")

            report += line + "\n"

        return report

    # _get_filestats()
    #
    # Gets the necessary information from a dictionary
    #
    # Args:
    #    directory (Directory): The base directory
    #    filename (str): A filename inside the directory
    #    filestat (FileStat): A FileStat for the filename
    #    list_long (Bool): whether to display verbose information about artifacts
    #
    # Returns:
    #    (str): The information about the element
    #
    def _get_filestats(self, directory, filename, filestat, list_long=False):
        if list_long:
            size = str(filestat.size)
            # Support files up to 99G, meaning maximum characters is 11
            max_v_len = 11
            if filestat.file_type == FileType.DIRECTORY:
                return (
                    "drwxr-xr-x  dir    {}".format(size)
                    + "{} ".format(" " * (max_v_len - len(size)))
                    + "{}".format(filename)
                )
            elif filestat.file_type == FileType.SYMLINK:
                target = directory.readlink(filename)
                return (
                    "lrwxrwxrwx  link   {}".format(size)
                    + "{} ".format(" " * (max_v_len - len(size)))
                    + "{} -> {}".format(filename, target)
                )
            elif filestat.executable:
                return (
                    "-rwxr-xr-x  exe    {}".format(size)
                    + "{} ".format(" " * (max_v_len - len(size)))
                    + "{}".format(filename)
                )
            else:
                return (
                    "-rw-r--r--  reg    {}".format(size)
                    + "{} ".format(" " * (max_v_len - len(size)))
                    + "{}".format(filename)
                )
        return filename
