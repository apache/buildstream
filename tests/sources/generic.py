import os
import pathlib

import pytest

from .fixture import Setup
from buildstream.exceptions import SourceError

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "generic",
)


@pytest.mark.datafiles(DATA_DIR)
def test_staging_to_existing(tmpdir, datafiles):
    setup = Setup(datafiles, 'elements/install-to-build.bst', tmpdir)

    # Create a file in the build directory (/buildstream/build)
    build_dir = pathlib.Path(os.path.join(setup.context.builddir,
                                          'buildstream', 'build'))
    build_dir.mkdir(parents=True)
    build_dir.joinpath('file').touch()

    # Ensure that we can't stage to an already filled build directory
    with pytest.raises(SourceError):
        setup.source._stage(setup.context.builddir)
