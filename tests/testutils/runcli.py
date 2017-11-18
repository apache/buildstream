import os
import sys
import itertools
import traceback
from contextlib import contextmanager, ExitStack
from click.testing import CliRunner
from ruamel import yaml
import pytest

# Import the main cli entrypoint
from buildstream._frontend.main import cli as bst_cli
from buildstream import _yaml

# Special private exception accessor, for test case purposes
from buildstream._exceptions import _get_last_exception


# Wrapper for the click.testing result
class Result():

    def __init__(self, result):
        self.exit_code = result.exit_code
        self.output = result.output
        self.exception = _get_last_exception()
        self.result = result


class Cli():

    def __init__(self, directory, verbose=True):
        self.directory = directory
        self.config = None
        self.cli_runner = CliRunner()
        self.verbose = verbose

    # configure():
    #
    # Serializes a user configuration into a buildstream.conf
    # to use for this test cli.
    #
    # Args:
    #    config (dict): The user configuration to use
    #
    def configure(self, config):
        self.config = config

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
    def run(self, configure=True, project=None, silent=False, env=None, cwd=None, args=None):
        if args is None:
            args = []

        with ExitStack() as stack:
            bst_args = []

            if silent:
                bst_args += ['--no-verbose']

            if configure:
                config_file = stack.enter_context(
                    configured(self.directory, self.config)
                )
                bst_args += ['--config', config_file]

            if project:
                bst_args += ['--directory', project]

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

            result = self.cli_runner.invoke(bst_cli, bst_args)

        # Some informative stdout we can observe when anything fails
        if self.verbose:
            command = "bst " + " ".join(bst_args)
            print("BuildStream exited with code {} for invocation:\n\t{}"
                  .format(result.exit_code, command))
            print("Program output was:\n{}".format(result.output))

            if result.exc_info and result.exc_info[0] != SystemExit:
                traceback.print_exception(*result.exc_info)

        return Result(result)

    # Fetch an element state by name by
    # invoking bst show on the project with the CLI
    #
    def get_element_state(self, project, element_name):
        result = self.run(project=project, silent=True, args=[
            'show',
            '--deps', 'none',
            '--format', '%{state}',
            '--downloadable',
            element_name
        ])
        assert result.exit_code == 0
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
        assert result.exit_code == 0
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

        assert result.exit_code == 0
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
        assert result.exit_code == 0
        return result.output.splitlines()


# Main fixture
#
# Use result = cli.run([arg1, arg2]) to run buildstream commands
#
@pytest.fixture()
def cli(tmpdir):
    directory = os.path.join(str(tmpdir), 'cache')
    os.makedirs(directory)
    return Cli(directory)


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

    config['sourcedir'] = os.path.join(directory, 'sources')
    config['builddir'] = os.path.join(directory, 'build')
    config['artifactdir'] = os.path.join(directory, 'artifacts')
    config['logdir'] = os.path.join(directory, 'logs')

    # Dump it and yield the filename for test scripts to feed it
    # to buildstream as an artument
    filename = os.path.join(directory, "buildstream.conf")
    _yaml.dump(config, filename)

    yield filename
