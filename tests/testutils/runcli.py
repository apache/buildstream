import os
from contextlib import contextmanager, ExitStack
from click.testing import CliRunner
import pytest

# Import the main cli entrypoint
from buildstream._frontend.main import cli as bst_cli
from buildstream import _yaml


class Cli():

    def __init__(self, directory):
        self.directory = directory
        self.config = None
        self.cli_runner = CliRunner()

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
    #    args (list): A list of arguments to pass buildstream
    #
    def run(self, configure=True, project=None, silent=False, args=None):
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
            result = self.cli_runner.invoke(bst_cli, bst_args)

            if result.exit_code != 0:
                command = "bst " + " ".join(bst_args)
                print("BuildStream exited with error code {} for invocation:\n\t{}"
                      .format(result.exit_code, command))
                print("Program output was:\n{}".format(result.output))

            return result

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
