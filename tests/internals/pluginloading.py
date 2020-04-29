from contextlib import contextmanager
import os
import pytest

from buildstream._project import Project
from buildstream._pipeline import Pipeline

from tests.testutils import dummy_context

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "pluginloading",)


@contextmanager
def create_pipeline(tmpdir, basedir, target):
    with dummy_context() as context:
        context.deploydir = os.path.join(str(tmpdir), "deploy")
        context.casdir = os.path.join(str(tmpdir), "cas")
        project = Project(basedir, context)

        pipeline = Pipeline(context, project, None)
        (targets,) = pipeline.load([(target,)])
        yield targets


@pytest.mark.datafiles(os.path.join(DATA_DIR, "customsource"))
def test_customsource(datafiles, tmpdir):

    basedir = str(datafiles)
    with create_pipeline(tmpdir, basedir, "simple.bst") as targets:
        assert targets[0].get_kind() == "autotools"


@pytest.mark.datafiles(os.path.join(DATA_DIR, "customelement"))
def test_customelement(datafiles, tmpdir):

    basedir = str(datafiles)
    with create_pipeline(tmpdir, basedir, "simple.bst") as targets:
        assert targets[0].get_kind() == "foo"
