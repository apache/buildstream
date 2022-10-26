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
"""
runcli - Test fixtures used for running BuildStream commands
============================================================

:function:'cli' Use result = cli.run([arg1, arg2]) to run buildstream commands

:function:'cli_integration' A variant of the main fixture that keeps persistent
                            artifact and source caches. It also does not use
                            the click test runner to avoid deadlock issues when
                            running `bst shell`, but unfortunately cannot produce
                            nice stacktraces.

"""


import os
import re
import sys
import shutil
import tempfile
import itertools
import traceback
from contextlib import contextmanager, ExitStack
from ruamel import yaml
import pytest

# XXX Using pytest private internals here
#
# We use pytest internals to capture the stdout/stderr during
# a run of the buildstream CLI. We do this because click's
# CliRunner convenience API (click.testing module) does not support
# separation of stdout/stderr.
#
from _pytest.capture import MultiCapture, FDCapture, FDCaptureBinary

# Import the main cli entrypoint
from buildstream._frontend import cli as bst_cli
from buildstream import _yaml, node
from buildstream._cas import CASCache
from buildstream.element import _get_normal_name, _compose_artifact_name

# Special private exception accessor, for test case purposes
from buildstream._exceptions import BstError, get_last_exception, get_last_task_error
from buildstream._protos.buildstream.v2 import artifact_pb2


# Wrapper for the click.testing result
class Result:
    def __init__(self, exit_code=None, exception=None, exc_info=None, output=None, stderr=None):
        self.exit_code = exit_code
        self.exc = exception
        self.exc_info = exc_info
        self.output = output
        self.stderr = stderr
        self.unhandled_exception = False

        # The last exception/error state is stored at exception
        # creation time in BstError(), but this breaks down with
        # recoverable errors where code blocks ignore some errors
        # and fallback to alternative branches.
        #
        # For this reason, we just ignore the exception and errors
        # in the case that the exit code reported is 0 (success).
        #
        if self.exit_code != 0:

            # Check if buildstream failed to handle an
            # exception, topevel CLI exit should always
            # be a SystemExit exception.
            #
            if not isinstance(exception, SystemExit):
                self.unhandled_exception = True

            self.exception = get_last_exception()
            self.task_error_domain, self.task_error_reason = get_last_task_error()
        else:
            self.exception = None
            self.task_error_domain = None
            self.task_error_reason = None

    # assert_success()
    #
    # Asserts that the buildstream session completed successfully
    #
    # Args:
    #    fail_message (str): An optional message to override the automatic
    #                        assertion error messages
    # Raises:
    #    (AssertionError): If the session did not complete successfully
    #
    def assert_success(self, fail_message=""):
        assert self.exit_code == 0, fail_message
        assert self.exc is None, fail_message
        assert self.exception is None, fail_message
        assert self.unhandled_exception is False

    # assert_main_error()
    #
    # Asserts that the buildstream session failed, and that
    # the main process error report is as expected
    #
    # Args:
    #    error_domain (ErrorDomain): The domain of the error which occurred
    #    error_reason (any): The reason field of the error which occurred
    #    fail_message (str): An optional message to override the automatic
    #                        assertion error messages
    #    debug (bool): If true, prints information regarding the exit state of the result()
    # Raises:
    #    (AssertionError): If any of the assertions fail
    #
    def assert_main_error(self, error_domain, error_reason, fail_message="", *, debug=False):
        if debug:
            print(
                """
                Exit code: {}
                Exception: {}
                Domain:    {}
                Reason:    {}
                """.format(
                    self.exit_code, self.exception, self.exception.domain, self.exception.reason
                )
            )
        assert self.exit_code == -1, fail_message
        assert self.exc is not None, fail_message
        assert self.exception is not None, fail_message
        assert isinstance(self.exception, BstError), fail_message
        assert self.unhandled_exception is False

        assert self.exception.domain == error_domain, fail_message
        assert self.exception.reason == error_reason, fail_message

    # assert_task_error()
    #
    # Asserts that the buildstream session failed, and that
    # the child task error which caused buildstream to exit
    # is as expected.
    #
    # Args:
    #    error_domain (ErrorDomain): The domain of the error which occurred
    #    error_reason (any): The reason field of the error which occurred
    #    fail_message (str): An optional message to override the automatic
    #                        assertion error messages
    # Raises:
    #    (AssertionError): If any of the assertions fail
    #
    def assert_task_error(self, error_domain, error_reason, fail_message=""):

        assert self.exit_code == -1, fail_message
        assert self.exc is not None, fail_message
        assert self.exception is not None, fail_message
        assert isinstance(self.exception, BstError), fail_message
        assert self.unhandled_exception is False

        assert self.task_error_domain == error_domain, fail_message
        assert self.task_error_reason == error_reason, fail_message

    # assert_shell_error()
    #
    # Asserts that the buildstream created a shell and that the task in the
    # shell failed.
    #
    # Args:
    #    fail_message (str): An optional message to override the automatic
    #                        assertion error messages
    # Raises:
    #    (AssertionError): If any of the assertions fail
    #
    def assert_shell_error(self, fail_message=""):
        assert self.exit_code == 1, fail_message

    # get_start_order()
    #
    # Gets the list of elements processed in a given queue, in the
    # order of their first appearances in the session.
    #
    # Args:
    #    activity (str): The queue activity name (like 'fetch')
    #
    # Returns:
    #    (list): A list of element names in the order which they first appeared in the result
    #
    def get_start_order(self, activity):
        results = re.findall(r"\[\s*{}:(\S+)\s*\]\s*START\s*.*\.log".format(activity), self.stderr)
        if results is None:
            return []
        return list(results)

    # get_tracked_elements()
    #
    # Produces a list of element names on which tracking occurred
    # during the session.
    #
    # This is done by parsing the buildstream stderr log
    #
    # Returns:
    #    (list): A list of element names
    #
    def get_tracked_elements(self):
        tracked = re.findall(r"\[\s*track:(\S+)\s*]", self.stderr)
        if tracked is None:
            return []

        return list(tracked)

    def get_built_elements(self):
        built = re.findall(r"\[\s*build:(\S+)\s*\]\s*SUCCESS\s*Caching artifact", self.stderr)
        if built is None:
            return []

        return list(built)

    def get_pushed_elements(self):
        pushed = re.findall(r"\[\s*push:(\S+)\s*\]\s*INFO\s*Pushed artifact", self.stderr)
        if pushed is None:
            return []

        return list(pushed)

    def get_pulled_elements(self):
        pulled = re.findall(r"\[\s*pull:(\S+)\s*\]\s*INFO\s*Pulled artifact", self.stderr)
        if pulled is None:
            return []

        return list(pulled)


class Cli:
    def __init__(self, directory, verbose=True, default_options=None):
        self.directory = directory
        self.config = None
        self.verbose = verbose
        self.artifact = TestArtifact()

        os.makedirs(directory)

        if default_options is None:
            default_options = []

        self.default_options = default_options

    # configure():
    #
    # Serializes a user configuration into a buildstream.conf
    # to use for this test cli.
    #
    # Args:
    #    config (dict): The user configuration to use
    #
    def configure(self, config):
        if self.config is None:
            self.config = {}

        for key, val in config.items():
            self.config[key] = val

    # remove_artifact_from_cache():
    #
    # Remove given element artifact from artifact cache
    #
    # Args:
    #    project (str): The project path under test
    #    element_name (str): The name of the element artifact
    #    cache_dir (str): Specific cache dir to remove artifact from
    #
    def remove_artifact_from_cache(self, project, element_name, *, cache_dir=None):
        # Read configuration to figure out where artifacts are stored
        if not cache_dir:
            default = os.path.join(project, "cache")

            if self.config is not None:
                cache_dir = self.config.get("cachedir", default)
            else:
                cache_dir = default

        self.artifact.remove_artifact_from_cache(cache_dir, element_name)

    # run():
    #
    # Runs buildstream with the given arguments, additionally
    # also passes some global options to buildstream in order
    # to stay contained in the testing environment.
    #
    # Args:
    #    project (str): An optional path to a project
    #    silent (bool): Whether to pass --no-verbose
    #    env (dict): Environment variables to temporarily set during the test
    #    args (list): A list of arguments to pass buildstream
    #    binary_capture (bool): Whether to capture the stdout/stderr as binary
    #
    def run(self, project=None, silent=False, env=None, cwd=None, options=None, args=None, binary_capture=False):

        # We don't want to carry the state of one bst invocation into another
        # bst invocation. Since node _FileInfo objects hold onto BuildStream
        # projects, this means that they would be also carried forward. This
        # becomes a problem when spawning new processes - when pickling the
        # state of the node module we will also be pickling elements from
        # previous bst invocations.
        node._reset_global_state()

        if args is None:
            args = []
        if options is None:
            options = []

        # We may have been passed e.g. pathlib.Path or py.path
        args = [str(x) for x in args]

        options = self.default_options + options

        with ExitStack() as stack:
            bst_args = ["--no-colors"]

            if silent:
                bst_args += ["--no-verbose"]

            config_file = stack.enter_context(configured(self.directory, self.config))
            bst_args += ["--config", config_file]

            if project:
                bst_args += ["--directory", str(project)]

            for option, value in options:
                bst_args += ["--option", option, value]

            bst_args += args

            if cwd is not None:
                stack.enter_context(chdir(cwd))

            if env is not None:
                stack.enter_context(environment(env))

            # Ensure we have a working stdout - required to work
            # around a bug that appears to cause AIX to close
            # sys.__stdout__ after setup.py
            try:
                sys.__stdout__.fileno()
            except ValueError:
                sys.__stdout__ = open("/dev/stdout", "w", encoding="utf-8")  # pylint: disable=consider-using-with

            result = self._invoke(bst_cli, bst_args, binary_capture=binary_capture)

        # Some informative stdout we can observe when anything fails
        if self.verbose:
            command = "bst " + " ".join(bst_args)
            print("BuildStream exited with code {} for invocation:\n\t{}".format(result.exit_code, command))
            if result.output:
                print("Program output was:\n{}".format(result.output))
            if result.stderr:
                print("Program stderr was:\n{}".format(result.stderr))

            if result.exc_info and result.exc_info[0] != SystemExit:
                traceback.print_exception(*result.exc_info)

        return result

    def _invoke(self, cli_object, args=None, binary_capture=False):
        exc_info = None
        exception = None
        exit_code = 0

        # Temporarily redirect sys.stdin to /dev/null to ensure that
        # Popen doesn't attempt to read pytest's dummy stdin.
        old_stdin = sys.stdin
        with open(os.devnull, "rb") as devnull:
            sys.stdin = devnull
            capture_kind = FDCaptureBinary if binary_capture else FDCapture
            capture = MultiCapture(out=capture_kind(1), err=capture_kind(2), in_=None)
            capture.start_capturing()

            try:
                cli_object.main(args=args or (), prog_name=cli_object.name)
            except SystemExit as e:
                if e.code != 0:
                    exception = e

                exc_info = sys.exc_info()

                exit_code = e.code
                if not isinstance(exit_code, int):
                    sys.stdout.write("Program exit code was not an integer: ")
                    sys.stdout.write(str(exit_code))
                    sys.stdout.write("\n")
                    exit_code = 1
            except Exception as e:  # pylint: disable=broad-except
                exception = e
                exit_code = -1
                exc_info = sys.exc_info()
            finally:
                sys.stdout.flush()

        sys.stdin = old_stdin
        out, err = capture.readouterr()
        capture.stop_capturing()

        return Result(exit_code=exit_code, exception=exception, exc_info=exc_info, output=out, stderr=err)

    # Fetch an element state by name by
    # invoking bst show on the project with the CLI
    #
    # If you need to get the states of multiple elements,
    # then use get_element_states(s) instead.
    #
    def get_element_state(self, project, element_name):
        result = self.run(
            project=project, silent=True, args=["show", "--deps", "none", "--format", "%{state}", element_name]
        )
        result.assert_success()
        return result.output.strip()

    # Fetch the states of elements for a given target / deps
    #
    # Returns a dictionary with the element names as keys
    #
    def get_element_states(self, project, targets, deps="all"):
        result = self.run(
            project=project, silent=True, args=["show", "--deps", deps, "--format", "%{name}||%{state}", *targets]
        )
        result.assert_success()
        lines = result.output.splitlines()
        states = {}
        for line in lines:
            split = line.split(sep="||")
            states[split[0]] = split[1]
        return states

    # Fetch an element's cache key by invoking bst show
    # on the project with the CLI
    #
    def get_element_key(self, project, element_name):
        result = self.run(
            project=project, silent=True, args=["show", "--deps", "none", "--format", "%{full-key}", element_name]
        )
        result.assert_success()
        return result.output.strip()

    # Get the decoded config of an element.
    #
    def get_element_config(self, project, element_name):
        result = self.run(
            project=project, silent=True, args=["show", "--deps", "none", "--format", "%{config}", element_name]
        )

        result.assert_success()
        return yaml.safe_load(result.output)

    # Fetch the elements that would be in the pipeline with the given
    # arguments.
    #
    def get_pipeline(self, project, elements, except_=None, scope="all"):
        if except_ is None:
            except_ = []

        args = ["show", "--deps", scope, "--format", "%{name}"]
        args += list(itertools.chain.from_iterable(zip(itertools.repeat("--except"), except_)))

        result = self.run(project=project, silent=True, args=args + elements)
        result.assert_success()
        return result.output.splitlines()

    # Fetch an element's complete artifact name, cache_key will be generated
    # if not given.
    #
    def get_artifact_name(self, project, project_name, element_name, cache_key=None):
        if not cache_key:
            cache_key = self.get_element_key(project, element_name)

        # Replace path separator and chop off the .bst suffix for normal name
        normal_name = _get_normal_name(element_name)
        return _compose_artifact_name(project_name, normal_name, cache_key)


class CliIntegration(Cli):

    # run()
    #
    # This supports the same arguments as Cli.run(), see run_project_config().
    #
    def run(self, project=None, silent=False, env=None, cwd=None, options=None, args=None, binary_capture=False):
        return self.run_project_config(
            project=project, silent=silent, env=env, cwd=cwd, options=options, args=args, binary_capture=binary_capture
        )

    # run_project_config()
    #
    # This supports the same arguments as Cli.run() and additionally
    # it supports the project_config keyword argument.
    #
    # This will first load the project.conf file from the specified
    # project directory ('project' keyword argument) and perform substitutions
    # of any {project_dir} specified in the existing project.conf.
    #
    # If the project_config parameter is specified, it is expected to
    # be a dictionary of additional project configuration options, and
    # will be composited on top of the already loaded project.conf
    #
    def run_project_config(self, *, project_config=None, **kwargs):

        # First load the project.conf and substitute {project_dir}
        #
        # Save the original project.conf, because we will run more than
        # once in the same temp directory
        #
        project_directory = kwargs["project"]
        project_filename = os.path.join(project_directory, "project.conf")
        project_backup = os.path.join(project_directory, "project.conf.backup")
        project_load_filename = project_filename

        if not os.path.exists(project_backup):
            shutil.copy(project_filename, project_backup)
        else:
            project_load_filename = project_backup

        with open(project_load_filename, encoding="utf-8") as f:
            config = f.read()
        config = config.format(project_dir=project_directory)

        if project_config is not None:

            # If a custom project configuration dictionary was
            # specified, composite it on top of the already
            # substituted base project configuration
            #
            base_config = _yaml.load_data(config)

            # In order to leverage _yaml.composite_dict(), both
            # dictionaries need to be loaded via _yaml.load_data() first
            #
            with tempfile.TemporaryDirectory(dir=project_directory) as scratchdir:

                temp_project = os.path.join(scratchdir, "project.conf")
                with open(temp_project, "w", encoding="utf-8") as f:
                    yaml.safe_dump(project_config, f)

                project_config = _yaml.load(temp_project, shortname="project.conf")

            project_config._composite(base_config)

            _yaml.roundtrip_dump(base_config, project_filename)

        else:

            # Otherwise, just dump it as is
            with open(project_filename, "w", encoding="utf-8") as f:
                f.write(config)

        return super().run(**kwargs)


class CliRemote(CliIntegration):

    # ensure_services():
    #
    # Make sure that required services are configured and that
    # non-required ones are not.
    #
    # Args:
    #    actions (bool): Whether to use the 'action-cache' service
    #    artifacts (bool): Whether to use the 'artifact-cache' service
    #    execution (bool): Whether to use the 'execution' service
    #    sources (bool): Whether to use the 'source-cache' service
    #    storage (bool): Whether to use the 'storage' service
    #
    # Returns a list of configured services (by names).
    #
    def ensure_services(self, actions=True, execution=True, storage=True, artifacts=False, sources=False):
        # Build a list of configured services by name:
        configured_services = []
        if not self.config:
            return configured_services

        if "remote-execution" in self.config:
            rexec_config = self.config["remote-execution"]

            if "action-cache-service" in rexec_config:
                if actions:
                    configured_services.append("action-cache")
                else:
                    rexec_config.pop("action-cache-service")

            if "execution-service" in rexec_config:
                if execution:
                    configured_services.append("execution")
                else:
                    rexec_config.pop("execution-service")

            if "storage-service" in rexec_config:
                if storage:
                    configured_services.append("storage")
                else:
                    rexec_config.pop("storage-service")

        if "artifacts" in self.config:
            if artifacts:
                configured_services.append("artifact-cache")
            else:
                self.config.pop("artifacts")

        if "source-caches" in self.config:
            if sources:
                configured_services.append("source-cache")
            else:
                self.config.pop("source-caches")

        return configured_services


class TestArtifact:

    # remove_artifact_from_cache():
    #
    # Remove given element artifact from artifact cache
    #
    # Args:
    #    cache_dir (str): Specific cache dir to remove artifact from
    #    element_name (str): The name of the element artifact
    #
    def remove_artifact_from_cache(self, cache_dir, element_name):

        cache_dir = os.path.join(cache_dir, "artifacts", "refs")

        normal_name = element_name.replace(os.sep, "-")
        cache_dir = os.path.splitext(os.path.join(cache_dir, "test", normal_name))[0]
        shutil.rmtree(cache_dir)

    # is_cached():
    #
    # Check if given element has a cached artifact
    #
    # Args:
    #    cache_dir (str): Specific cache dir to check
    #    element (Element): The element object
    #    element_key (str): The element's cache key
    #
    # Returns:
    #   (bool): If the cache contains the element's artifact
    #
    def is_cached(self, cache_dir, element, element_key):

        # cas = CASCache(str(cache_dir))
        artifact_ref = element.get_artifact_name(element_key)
        return os.path.exists(os.path.join(cache_dir, "artifacts", "refs", artifact_ref))

    # get_digest():
    #
    # Get the digest for a given element's artifact files
    #
    # Args:
    #    cache_dir (str): Specific cache dir to check
    #    element (Element): The element object
    #    element_key (str): The element's cache key
    #
    # Returns:
    #   (Digest): The digest stored in the ref
    #
    def get_digest(self, cache_dir, element, element_key):

        artifact_ref = element.get_artifact_name(element_key)
        artifact_dir = os.path.join(cache_dir, "artifacts", "refs")
        artifact_proto = artifact_pb2.Artifact()
        with open(os.path.join(artifact_dir, artifact_ref), "rb") as f:
            artifact_proto.ParseFromString(f.read())
        return artifact_proto.files

    # extract_buildtree():
    #
    # Context manager for extracting an elements artifact buildtree for
    # inspection.
    #
    # Args:
    #    tmpdir (LocalPath): pytest fixture for the tests tmp dir
    #    digest (Digest): The element directory digest to extract
    #
    # Yields:
    #    (str): path to extracted buildtree directory, does not guarantee
    #           existence.
    @contextmanager
    def extract_buildtree(self, cache_dir, tmpdir, ref):
        artifact = artifact_pb2.Artifact()
        try:
            with open(os.path.join(cache_dir, "artifacts", "refs", ref), "rb") as f:
                artifact.ParseFromString(f.read())
        except FileNotFoundError:
            yield None
        else:
            if str(artifact.buildtree):
                with self._extract_subdirectory(tmpdir, artifact.buildtree) as f:
                    yield f
            else:
                yield None

    # _extract_subdirectory():
    #
    # Context manager for extracting an element artifact for inspection,
    # providing an expected path for a given subdirectory
    #
    # Args:
    #    tmpdir (LocalPath): pytest fixture for the tests tmp dir
    #    digest (Digest): The element directory digest to extract
    #    subdir (str): Subdirectory to path
    #
    # Yields:
    #    (str): path to extracted subdir directory, does not guarantee
    #           existence.
    @contextmanager
    def _extract_subdirectory(self, tmpdir, digest):
        with tempfile.TemporaryDirectory() as extractdir:
            try:
                cas = CASCache(str(tmpdir), casd=False)
                cas.checkout(extractdir, digest)
                yield extractdir
            except FileNotFoundError:
                yield None


# Main fixture
#
# Use result = cli.run([arg1, arg2]) to run buildstream commands
#
@pytest.fixture()
def cli(tmpdir):
    directory = os.path.join(str(tmpdir), "cache")
    return Cli(directory)


# A variant of the main fixture that keeps persistent artifact and
# source caches.
#
# It also does not use the click test runner to avoid deadlock issues
# when running `bst shell`, but unfortunately cannot produce nice
# stacktraces.
@pytest.fixture()
def cli_integration(tmpdir, integration_cache):
    directory = os.path.join(str(tmpdir), "cache")
    fixture = CliIntegration(directory)

    # We want to cache sources for integration tests more permanently,
    # to avoid downloading the huge base-sdk repeatedly
    fixture.configure(
        {
            "cachedir": integration_cache.cachedir,
            "sourcedir": integration_cache.sources,
        }
    )

    yield fixture

    # remove following folders if necessary
    try:
        shutil.rmtree(os.path.join(integration_cache.cachedir, "build"))
    except FileNotFoundError:
        pass
    try:
        shutil.rmtree(os.path.join(integration_cache.cachedir, "tmp"))
    except FileNotFoundError:
        pass


# A variant of the main fixture that is configured for remote-execution.
#
# It also does not use the click test runner to avoid deadlock issues
# when running `bst shell`, but unfortunately cannot produce nice
# stacktraces.
@pytest.fixture()
def cli_remote_execution(tmpdir, remote_services):
    directory = os.path.join(str(tmpdir), "cache")
    fixture = CliRemote(directory)

    artifacts = []
    if remote_services.artifact_service:
        artifacts.append({"url": remote_services.artifact_service, "push": True})
    if remote_services.artifact_index_service:
        artifacts.append({"url": remote_services.artifact_index_service, "push": True, "type": "index"})
    if remote_services.artifact_storage_service:
        artifacts.append({"url": remote_services.artifact_storage_service, "push": True, "type": "storage"})
    if artifacts:
        fixture.configure({"artifacts": {"servers": artifacts}})

    remote_execution = {}
    if remote_services.action_service:
        remote_execution["action-cache-service"] = {
            "url": remote_services.action_service,
        }
    if remote_services.exec_service:
        remote_execution["execution-service"] = {
            "url": remote_services.exec_service,
        }
    if remote_services.storage_service:
        remote_execution["storage-service"] = {
            "url": remote_services.storage_service,
        }
    if remote_execution:
        fixture.configure({"remote-execution": remote_execution})

    if remote_services.source_service:
        fixture.configure(
            {
                "source-caches": {
                    "servers": [
                        {
                            "url": remote_services.source_service,
                        }
                    ]
                }
            }
        )

    return fixture


@contextmanager
def chdir(directory):
    old_dir = os.getcwd()
    os.chdir(directory)
    yield
    os.chdir(old_dir)


@contextmanager
def environment(env):

    old_env = {}
    for key, value in env.items():
        old_env[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    yield

    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@contextmanager
def configured(directory, config=None):

    # Ensure we've at least relocated the caches to a temp directory
    if not config:
        config = {}

    if not config.get("sourcedir", False):
        config["sourcedir"] = os.path.join(directory, "sources")
    if not config.get("cachedir", False):
        config["cachedir"] = directory
    if not config.get("logdir", False):
        config["logdir"] = os.path.join(directory, "logs")

    cas_stage_root = os.environ.get("BST_CAS_STAGING_ROOT")
    if cas_stage_root:
        symlink_path = os.path.join(config["cachedir"], "cas", "staging")
        if not os.path.lexists(symlink_path):
            os.makedirs(os.path.join(config["cachedir"], "cas"), exist_ok=True)
            os.symlink(cas_stage_root, symlink_path)

    # Dump it and yield the filename for test scripts to feed it
    # to buildstream as an artument
    filename = os.path.join(directory, "buildstream.conf")
    _yaml.roundtrip_dump(config, filename)

    yield filename
