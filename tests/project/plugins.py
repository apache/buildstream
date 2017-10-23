import os
import pytest

from buildstream._context import Context
from buildstream._project import Project
from buildstream._pipeline import Pipeline

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'data',
)


def create_pipeline(tmpdir, basedir, target):
    context = Context()
    project = Project(basedir, context)
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')

    def dummy_handler(message, context):
        pass

    context._set_message_handler(dummy_handler)

    return Pipeline(context, project, [target], [])


# We've already validated that the plugin system works in
# other tests, here we just want to load a custom plugin
# and see if some of our configuration ended up on it, and
# also test that the project's configuration of plugin
# paths is actually working.
#
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'plugins'))
def test_custom_element(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'custom.bst')

    element = pipeline.targets[0]
    assert(len(element._Element__sources) > 0)
    source = element._Element__sources[0]

    assert(element.get_kind() == "custom")
    assert(source.get_kind() == "custom")

    assert(element.configuration == "pony")
    assert(source.configuration == "pony")
