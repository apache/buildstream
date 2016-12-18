import os
import pytest
import tempfile

from pluginbase import PluginBase
from buildstream import Context, Project
from buildstream import SourceError
from buildstream._loader import Loader
from buildstream._sourcefactory import SourceFactory

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'local',
)


# Hacked hand fashioned fixture, just a helper function
# because it's tricky to have a pytest fixture take arguments
#
# datafiles: A project directory datafiles
# target: A target element bst file
#
class Setup():

    def __init__(self, datafiles, target):
        directory = os.path.join(datafiles.dirname, datafiles.basename)

        self.context = Context('x86_64')
        self.project = Project(directory)

        loader = Loader(directory, target, None, None)
        element = loader.load()
        assert(len(element.sources) == 1)
        self.meta_source = element.sources[0]

        base = PluginBase(package='buildstream.plugins')
        self.factory = SourceFactory(base)
        self.source = self.factory.create(self.meta_source.kind,
                                          self.context,
                                          self.project,
                                          self.meta_source)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_create_source(datafiles):
    setup = Setup(datafiles, 'target.bst')
    assert(setup.source.get_kind() == 'local')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_preflight(datafiles):
    setup = Setup(datafiles, 'target.bst')
    assert(setup.source.get_kind() == 'local')

    # Just expect that this passes without throwing any exception
    setup.source.preflight()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_preflight_fail(datafiles):
    setup = Setup(datafiles, 'target.bst')
    assert(setup.source.get_kind() == 'local')

    # Delete the file which the local source wants
    localfile = os.path.join(datafiles.dirname, datafiles.basename, 'file.txt')
    os.remove(localfile)

    # Expect a preflight error
    with pytest.raises(SourceError) as exc:
        setup.source.preflight()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_unique_key(datafiles):
    setup = Setup(datafiles, 'target.bst')
    assert(setup.source.get_kind() == 'local')

    # Get the unique key
    unique_key = setup.source.get_unique_key()

    # No easy way to test this, let's just check that the
    # returned 'thing' is an array of tuples and the first element
    # of the first tuple is the filename, and the second is not falsy
    assert(isinstance(unique_key, list))
    assert(len(unique_key) == 1)
    filename, digest = unique_key[0]
    assert(filename == 'file.txt')
    assert(digest)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst')
    assert(setup.source.get_kind() == 'local')

    with tempfile.TemporaryDirectory(dir=str(tmpdir)) as directory:
        setup.source.stage(directory)
        assert(os.path.exists(os.path.join(directory, 'file.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'directory'))
def test_stage_directory(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst')
    assert(setup.source.get_kind() == 'local')

    with tempfile.TemporaryDirectory(dir=str(tmpdir)) as directory:
        setup.source.stage(directory)
        assert(os.path.exists(os.path.join(directory, 'file.txt')))
        assert(os.path.exists(os.path.join(directory, 'subdir', 'anotherfile.txt')))
