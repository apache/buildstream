import os

from pluginbase import PluginBase
from buildstream import Context, Project
from buildstream._loader import Loader
from buildstream._sourcefactory import SourceFactory


def message_handler(message, context):
    print("{}".format(message.message))


# Hacked hand fashioned fixture, just a helper function
# because its tricky to have a pytest fixture take arguments
#
# datafiles: A project directory datafiles
# target: A target element bst file
#
class Setup():

    def __init__(self, datafiles, target, tmpdir):
        directory = os.path.join(datafiles.dirname, datafiles.basename)

        self.context = Context([])
        self.project = Project(directory, self.context)

        # A message handler is required
        self.context._set_message_handler(message_handler)

        self.context.sourcedir = os.path.join(str(tmpdir), 'sources')
        self.context.builddir = os.path.join(str(tmpdir), 'build')

        if not os.path.exists(self.context.sourcedir):
            os.mkdir(self.context.sourcedir)
        if not os.path.exists(self.context.builddir):
            os.mkdir(self.context.builddir)

        loader = Loader(directory, [target], self.project._options)
        element = loader.load()[0]

        # Allow repo aliases to access files in the directories using tmpdir and datafiles
        self.project._aliases['tmpdir'] = "file:///" + str(tmpdir)
        self.project._aliases['datafiles'] = "file:///" + str(datafiles)

        assert(len(element.sources) >= 1)

        base = PluginBase(package='buildstream.plugins')
        self.factory = SourceFactory(base)

        self.sources = [self.factory.create(source.kind,
                                            self.context,
                                            self.project,
                                            source)
                        for source in element.sources]
        self.source = self.sources[0]
