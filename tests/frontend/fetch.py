# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from tests.testutils import generate_junction, yaml_file_get_provenance
from buildstream.testing import create_repo
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

from . import configure_project

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, 'project')


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'project_world'))
def test_fetch_default_targets(cli, tmpdir, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, 'elements')
    element_name = 'fetch-test.bst'

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(project)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == 'fetch needed'

    # Now try to fetch it, using the default target feature
    result = cli.run(project=project, args=['source', 'fetch'])
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == 'buildable'


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_fetch_consistency_error(cli, datafiles):
    project = str(datafiles)

    # When the error occurs outside of the scheduler at load time,
    # then the SourceError is reported directly as the main error.
    result = cli.run(project=project, args=['source', 'fetch', 'error.bst'])
    result.assert_main_error(ErrorDomain.SOURCE, 'the-consistency-error')


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_fetch_consistency_bug(cli, datafiles):
    project = str(datafiles)

    # FIXME:
    #
    #    When a plugin raises an unhandled exception at load
    #    time, as is the case when running Source.get_consistency()
    #    for a fetch command, we could report this to the user
    #    more gracefully as a BUG message.
    #
    result = cli.run(project=project, args=['source', 'fetch', 'bug.bst'])
    assert result.exc is not None
    assert str(result.exc) == "Something went terribly wrong"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_unfetched_junction(cli, tmpdir, datafiles, ref_storage):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create a repo to hold the subproject and generate a junction element for it
    ref = generate_junction(tmpdir, subproject_path, junction_path, store_ref=(ref_storage == 'inline'))

    # Create a stack element to depend on a cross junction element
    #
    element = {
        'kind': 'stack',
        'depends': [
            {
                'junction': 'junction.bst',
                'filename': 'import-etc.bst'
            }
        ]
    }
    _yaml.dump(element, element_path)

    # Dump a project.refs if we're using project.refs storage
    #
    if ref_storage == 'project.refs':
        project_refs = {
            'projects': {
                'test': {
                    'junction.bst': [
                        {
                            'ref': ref
                        }
                    ]
                }
            }
        }
        _yaml.dump(project_refs, os.path.join(project, 'junction.refs'))

    # Now try to fetch it, this should automatically result in fetching
    # the junction itself.
    result = cli.run(project=project, args=['source', 'fetch', 'junction-dep.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    configure_project(project, {
        'ref-storage': ref_storage
    })

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path, store_ref=False)

    # Create a stack element to depend on a cross junction element
    #
    element = {
        'kind': 'stack',
        'depends': [
            {
                'junction': 'junction.bst',
                'filename': 'import-etc.bst'
            }
        ]
    }
    _yaml.dump(element, element_path)

    # Now try to fetch it, this will bail with the appropriate error
    # informing the user to track the junction first
    result = cli.run(project=project, args=['source', 'fetch', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)

    # Assert that we have the expected provenance encoded into the error
    provenance = yaml_file_get_provenance(
        element_path, 'junction-dep.bst', key='depends', indices=[0])
    assert str(provenance) in result.stderr
