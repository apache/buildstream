from buildstream._context import Context
from buildstream._project import Project
from buildstream._loader import Loader


#
# This is used by the loader test modules, these should
# be removed in favor of testing the functionality via
# the CLI like in the frontend tests anyway.
#
def make_loader(basedir):
    context = Context()
    project = Project(basedir, context)
    return project.loader
