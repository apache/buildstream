import os
import re
import sys
import shutil
import tempfile
import itertools
import traceback
import subprocess
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
from _pytest.capture import MultiCapture, FDCapture

# Import the main cli entrypoint
from buildstream._frontend import cli as bst_cli
from buildstream import _yaml

# Special private exception accessor, for test case purposes
from buildstream._exceptions import BstError, get_last_exception, get_last_task_error


# Wrapper for the click.testing result
class Result():

    def __init__(self,
                 exit_code=None,
                 exception=None,
                 exc_info=None,
                 output=None,
                 stderr=None):
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
            self.task_error_domain, \
                self.task_error_reason = get_last_task_error()
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
    def assert_success(self, fail_message=''):
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
    def assert_main_error(self,
                          error_domain,
                          error_reason,
                          fail_message='',
                          *, debug=False):
        if debug:
            print(
                """
                Exit code: {}
                Exception: {}
                Domain:    {}
                Reason:    {}
                """.format(
                    self.exit_code,
                    self.exception,
                    self.exception.domain,
                    self.exception.reason
                ))
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
    def assert_task_error(self,
                          error_domain,
                          error_reason,
                          fail_message=''):

        assert self.exit_code == -1, fail_message
        assert self.exc is not None, fail_message
        assert self.exception is not None, fail_message
        assert isinstance(self.exception, BstError), fail_message
        assert self.unhandled_exception is False

        assert self.task_error_domain == error_domain, fail_message
        assert self.task_error_reason == error_reason, fail_message

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
        tracked = re.findall(r'\[track:(\S+)\s*]', self.stderr)
        if tracked is None:
            return []

        return list(tracked)

    def get_pushed_elements(self):
        pushed = re.findall(r'\[\s*push:(\S+)\s*\]\s*INFO\s*Pushed artifact', self.stderr)
        if pushed is None:
            return []

        return list(pushed)

    def get_pulled_elements(self):
        pulled = re.findall(r'\[\s*pull:(\S+)\s*\]\s*INFO\s*Pulled artifact', self.stderr)
        if pulled is None:
            return []

        return list(pulled)


class Cli():

    def __init__(self, directory, verbose=True, default_options=None):
        self.directory = directory
        self.config = None
        self.verbose = verbose

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

    def remove_artifact_from_cache(self, project, element_name,
                                   *, cache_dir=None):
        if not cache_dir:
            cache_dir = os.path.join(project, 'cache', 'artifacts')

        cache_dir = os.path.join(cache_dir, 'cas', 'refs', 'heads')

        cache_dir = os.path.splitext(os.path.join(cache_dir, 'test', element_name))[0]
        shutil.rmtree(cache_dir)

    # run():
    #
    # Runs buildstream with the given arguments, additionally
    # also passes some global options to buildstream in order
    # to stay contained in the testing environment.
    #
    # Args:
    #    configure (bool): Whether to pass a --config argument
    #    project (str): An optional path to a project
    #    silent (bool): Whether to pass --no-verbose
    #    env (dict): Environment variables to temporarily set during the test
    #    args (list): A list of arguments to pass buildstream
    #
    def run(self, configure=True, project=None, silent=False, env=None,
            cwd=None, options=None, args=None):
        if args is None:
            args = []
        if options is None:
            options = []

        options = self.default_options + options

        with ExitStack() as stack:
            bst_args = ['--no-colors']

            if silent:
                bst_args += ['--no-verbose']

            if configure:
                config_file = stack.enter_context(
                    configured(self.directory, self.config)
                )
                bst_args += ['--config', config_file]

            if project:
                bst_args += ['--directory', project]

            for option, value in options:
                bst_args += ['--option', option, value]

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
                sys.__stdout__ = open('/dev/stdout', 'w')

            result = self.invoke(bst_cli, bst_args)

        # Some informative stdout we can observe when anything fails
        if self.verbose:
            command = "bst " + " ".join(bst_args)
            print("BuildStream exited with code {} for invocation:\n\t{}"
                  .format(result.exit_code, command))
            if result.output:
                print("Program output was:\n{}".format(result.output))
            if result.stderr:
                print("Program stderr was:\n{}".format(result.stderr))

            if result.exc_info and result.exc_info[0] != SystemExit:
                traceback.print_exception(*result.exc_info)

        return result

    def invoke(self, cli, args=None, color=False, **extra):
        exc_info = None
        exception = None
        exit_code = 0

        # Temporarily redirect sys.stdin to /dev/null to ensure that
        # Popen doesn't attempt to read pytest's dummy stdin.
        old_stdin = sys.stdin
        with open(os.devnull) as devnull:
            sys.stdin = devnull

            capture = MultiCapture(out=True, err=True, in_=False, Capture=FDCapture)
            capture.start_capturing()

            try:
                cli.main(args=args or (), prog_name=cli.name, **extra)
            except SystemExit as e:
                if e.code != 0:
                    exception = e

                exc_info = sys.exc_info()

                exit_code = e.code
                if not isinstance(exit_code, int):
                    sys.stdout.write('Program exit code was not an integer: ')
                    sys.stdout.write(str(exit_code))
                    sys.stdout.write('\n')
                    exit_code = 1
            except Exception as e:
                exception = e
                exit_code = -1
                exc_info = sys.exc_info()
            finally:
                sys.stdout.flush()

        sys.stdin = old_stdin
        out, err = capture.readouterr()
        capture.stop_capturing()

        return Result(exit_code=exit_code,
                      exception=exception,
                      exc_info=exc_info,
                      output=out,
                      stderr=err)

    # Fetch an element state by name by
    # invoking bst show on the project with the CLI
    #
    def get_element_state(self, project, element_name):
        result = self.run(project=project, silent=True, args=[
            'show',
            '--deps', 'none',
            '--format', '%{state}',
            element_name
        ])
        result.assert_success()
        return result.output.strip()

    # Fetch an element's cache key by invoking bst show
    # on the project with the CLI
    #
    def get_element_key(self, project, element_name):
        result = self.run(project=project, silent=True, args=[
            'show',
            '--deps', 'none',
            '--format', '%{full-key}',
            element_name
        ])
        result.assert_success()
        return result.output.strip()

    # Get the decoded config of an element.
    #
    def get_element_config(self, project, element_name):
        result = self.run(project=project, silent=True, args=[
            'show',
            '--deps', 'none',
            '--format', '%{config}',
            element_name
        ])

        result.assert_success()
        return yaml.safe_load(result.output)

    # Fetch the elements that would be in the pipeline with the given
    # arguments.
    #
    def get_pipeline(self, project, elements, except_=None, scope='plan'):
        if except_ is None:
            except_ = []

        args = ['show', '--deps', scope, '--format', '%{name}']
        args += list(itertools.chain.from_iterable(zip(itertools.repeat('--except'), except_)))

        result = self.run(project=project, silent=True, args=args + elements)
        result.assert_success()
        return result.output.splitlines()


class CliIntegration(Cli):

    # run()
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
    def run(self, *args, project_config=None, **kwargs):

        # First load the project.conf and substitute {project_dir}
        #
        # Save the original project.conf, because we will run more than
        # once in the same temp directory
        #
        project_directory = kwargs['project']
        project_filename = os.path.join(project_directory, 'project.conf')
        project_backup = os.path.join(project_directory, 'project.conf.backup')
        project_load_filename = project_filename

        if not os.path.exists(project_backup):
            shutil.copy(project_filename, project_backup)
        else:
            project_load_filename = project_backup

        with open(project_load_filename) as f:
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

                temp_project = os.path.join(scratchdir, 'project.conf')
                with open(temp_project, 'w') as f:
                    yaml.safe_dump(project_config, f)

                project_config = _yaml.load(temp_project)

            _yaml.composite_dict(base_config, project_config)

            base_config = _yaml.node_sanitize(base_config)
            _yaml.dump(base_config, project_filename)

        else:

            # Otherwise, just dump it as is
            with open(project_filename, 'w') as f:
                f.write(config)

        return super().run(*args, **kwargs)


# Main fixture
#
# Use result = cli.run([arg1, arg2]) to run buildstream commands
#
@pytest.fixture()
def cli(tmpdir):
    directory = os.path.join(str(tmpdir), 'cache')
    os.makedirs(directory)
    return Cli(directory)


# A variant of the main fixture that keeps persistent artifact and
# source caches.
#
# It also does not use the click test runner to avoid deadlock issues
# when running `bst shell`, but unfortunately cannot produce nice
# stacktraces.
@pytest.fixture()
def cli_integration(tmpdir, integration_cache):
    directory = os.path.join(str(tmpdir), 'cache')
    os.makedirs(directory)

    if os.environ.get('BST_FORCE_BACKEND') == 'unix':
        fixture = CliIntegration(directory, default_options=[('linux', 'False')])
    else:
        fixture = CliIntegration(directory)

    # We want to cache sources for integration tests more permanently,
    # to avoid downloading the huge base-sdk repeatedly
    fixture.configure({
        'sourcedir': os.path.join(integration_cache, 'sources'),
        'artifactdir': os.path.join(integration_cache, 'artifacts')
    })

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
        os.environ[key] = value

    yield

    for key, value in old_env.items():
        if value is None:
            del os.environ[key]
        else:
            os.environ[key] = value


@contextmanager
def configured(directory, config=None):

    # Ensure we've at least relocated the caches to a temp directory
    if not config:
        config = {}

    if not config.get('sourcedir', False):
        config['sourcedir'] = os.path.join(directory, 'sources')
    if not config.get('builddir', False):
        config['builddir'] = os.path.join(directory, 'build')
    if not config.get('artifactdir', False):
        config['artifactdir'] = os.path.join(directory, 'artifacts')
    if not config.get('logdir', False):
        config['logdir'] = os.path.join(directory, 'logs')

    # Dump it and yield the filename for test scripts to feed it
    # to buildstream as an artument
    filename = os.path.join(directory, "buildstream.conf")
    _yaml.dump(config, filename)

    yield filename
