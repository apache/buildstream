from buildstream._context import Context
from buildstream._project import Project


#
# This is used by the loader test modules, these should
# be removed in favor of testing the functionality via
# the CLI like in the frontend tests anyway.
#
def make_project(basedir):
    return Project(basedir, Context())
