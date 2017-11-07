import os
import pytest

from buildstream import BuildElement
from buildstream._context import Context
from buildstream._project import Project
from buildstream._pipeline import Pipeline
from buildstream._platform import Platform

from tests.testutils.site import HAVE_ROOT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
)


def create_pipeline(tmpdir, basedir, target):
    context = Context([])
    project = Project(basedir, context)
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context._platform = Platform.get_platform()

    return Pipeline(context, project, [target], [])


def assert_command(datafiles, tmpdir, target, command, expected):
    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, target)
    assert(isinstance(pipeline.targets[0], BuildElement))

    commands = pipeline.targets[0].commands
    assert(commands.get(command) is not None)
    assert(len(commands[command]) > 0)

    print("Commands:\n{}".format(commands[command][0]))
    print("Expected:\n{}".format(expected))

    assert(commands[command][0] == expected)


###############################################################
#  Test proper loading of some default commands from plugins  #
###############################################################
@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.parametrize("target,command,expected", [
    ('autotools.bst', 'install-commands', "make -j1 DESTDIR=\"/buildstream/install\" install"),
    ('cmake.bst', 'configure-commands',
     "cmake -DCMAKE_INSTALL_PREFIX:PATH=\"/usr\" \\\n" +
     "-DCMAKE_INSTALL_LIBDIR=lib"),
    ('distutils.bst', 'install-commands',
     "python3 setup.py install --prefix \"/usr\" \\\n" +
     "--root \"/buildstream/install\""),
    ('makemaker.bst', 'configure-commands', "perl Makefile.PL PREFIX=/buildstream/install/usr"),
    ('modulebuild.bst', 'configure-commands', "perl Build.PL --prefix \"/buildstream/install/usr\""),
    ('qmake.bst', 'install-commands', "make -j1 INSTALL_ROOT=\"/buildstream/install\" install"),
])
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'defaults'))
def test_defaults(datafiles, tmpdir, target, command, expected):
    assert_command(datafiles, tmpdir, target, command, expected)


################################################################
#  Test overriding of variables to produce different commands  #
################################################################
@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.parametrize("target,command,expected", [
    ('autotools.bst', 'install-commands', "make -j1 DESTDIR=\"/custom/install/root\" install"),
    ('cmake.bst', 'configure-commands',
     "cmake -DCMAKE_INSTALL_PREFIX:PATH=\"/opt\" \\\n" +
     "-DCMAKE_INSTALL_LIBDIR=lib"),
    ('distutils.bst', 'install-commands',
     "python3 setup.py install --prefix \"/opt\" \\\n" +
     "--root \"/custom/install/root\""),
    ('makemaker.bst', 'configure-commands', "perl Makefile.PL PREFIX=/custom/install/root/opt"),
    ('modulebuild.bst', 'configure-commands', "perl Build.PL --prefix \"/custom/install/root/opt\""),
    ('qmake.bst', 'install-commands', "make -j1 INSTALL_ROOT=\"/custom/install/root\" install"),
])
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'overrides'))
def test_overrides(datafiles, tmpdir, target, command, expected):
    assert_command(datafiles, tmpdir, target, command, expected)
