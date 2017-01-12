import os

from pluginbase import PluginBase
from buildstream import Context, Project
from buildstream._loader import Loader
from buildstream._sourcefactory import SourceFactory


# Hacked hand fashioned fixture, just a helper function
# because it's tricky to have a pytest fixture take arguments
#
# datafiles: A project directory datafiles
# target: A target element bst file
#
class Setup():

    def __init__(self, datafiles, target, tmpdir):
        directory = os.path.join(datafiles.dirname, datafiles.basename)

        self.context = Context('x86_64')
        self.project = Project(directory)

        self.context.sourcedir = os.path.join(str(tmpdir), 'sources')
        self.context.builddir = os.path.join(str(tmpdir), 'build')

        if not os.path.exists(self.context.sourcedir):
            os.mkdir(self.context.sourcedir)
        if not os.path.exists(self.context.builddir):
            os.mkdir(self.context.builddir)

        loader = Loader(directory, target, None, None)
        element = loader.load()
        assert(len(element.sources) == 1)
        self.meta_source = element.sources[0]

        base = PluginBase(package='buildstream.plugins')
        self.factory = SourceFactory(base)
        self.source = self.factory.create(self.meta_source.kind,
                                          "test",
                                          self.context,
                                          self.project,
                                          self.meta_source)
