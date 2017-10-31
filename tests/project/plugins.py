import os
import pytest

from buildstream import Context, Project, Scope
from buildstream._pipeline import Pipeline
from buildstream._platform import Platform

from tests.testutils.site import HAVE_ROOT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)


def create_pipeline(tmpdir, basedir, target):
    context = Context([], 'x86_64')
    project = Project(basedir, context)
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')
    context._platform = Platform.get_platform()

    return Pipeline(context, project, target)


# We've already validated that the plugin system works in
# other tests, here we just want to load a custom plugin
# and see if some of our configuration ended up on it, and
# also test that the project's configuration of plugin
# paths is actually working.
#
@pytest.mark.skipif(not HAVE_ROOT, reason="requires root permissions")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'plugins'))
def test_custom_element(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'custom.bst')

    element = pipeline.target
    assert(len(element._Element__sources) > 0)
    source = element._Element__sources[0]

    assert(element.get_kind() == "custom")
    assert(source.get_kind() == "custom")

    assert(element.configuration == "pony")
    assert(source.configuration == "pony")
