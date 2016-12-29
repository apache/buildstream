import os
import pytest

from buildstream import Context, Project
from buildstream._pipeline import Pipeline

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'load',
)


def create_pipeline(tmpdir, basedir, target, variant):
    context = Context('x86_64')
    project = Project(basedir)

    context.deploydir = os.path.join(str(tmpdir), 'deploy')
    context.artifactdir = os.path.join(str(tmpdir), 'artifact')

    return Pipeline(context, project, target, variant)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'simple'))
def test_load_simple(datafiles, tmpdir):

    basedir = os.path.join(datafiles.dirname, datafiles.basename)
    pipeline = create_pipeline(tmpdir, basedir, 'simple.bst', None)

    assert(pipeline.target.get_kind() == "autotools")

    assert(isinstance(pipeline.target.commands['configure-commands'], list))
    command_list = pipeline.target.commands['configure-commands']
    assert(len(command_list) == 1)
    assert(command_list[0] == 'pony')
