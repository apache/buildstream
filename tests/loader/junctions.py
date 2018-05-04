import os
import pytest
import shutil

from buildstream import _yaml, ElementError
from buildstream._exceptions import LoadError, LoadErrorReason
from tests.testutils import cli, create_repo
from tests.testutils.site import HAVE_GIT


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'junctions',
)


def copy_subprojects(project, datafiles, subprojects):
    for subproject in subprojects:
        shutil.copytree(os.path.join(str(datafiles), subproject), os.path.join(str(project), subproject))


@pytest.mark.datafiles(DATA_DIR)
def test_simple_pipeline(cli, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    copy_subprojects(project, datafiles, ['base'])

    # Check that the pipeline includes the subproject element
    element_list = cli.get_pipeline(project, ['target.bst'])
    assert 'base.bst:target.bst' in element_list


@pytest.mark.datafiles(DATA_DIR)
def test_simple_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    copy_subprojects(project, datafiles, ['base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected files from both projects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'foo.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_nested_simple(cli, tmpdir, datafiles):
    foo = os.path.join(str(datafiles), 'foo')
    copy_subprojects(foo, datafiles, ['base'])

    project = os.path.join(str(datafiles), 'nested')
    copy_subprojects(project, datafiles, ['foo'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected files from all subprojects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'foo.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_nested_double(cli, tmpdir, datafiles):
    foo = os.path.join(str(datafiles), 'foo')
    copy_subprojects(foo, datafiles, ['base'])

    bar = os.path.join(str(datafiles), 'bar')
    copy_subprojects(bar, datafiles, ['base'])

    project = os.path.join(str(datafiles), 'toplevel')
    copy_subprojects(project, datafiles, ['base', 'foo', 'bar'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected files from all subprojects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'foo.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'bar.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_nested_conflict(cli, datafiles):
    foo = os.path.join(str(datafiles), 'foo')
    copy_subprojects(foo, datafiles, ['base'])

    bar = os.path.join(str(datafiles), 'bar')
    copy_subprojects(bar, datafiles, ['base'])

    project = os.path.join(str(datafiles), 'conflict')
    copy_subprojects(project, datafiles, ['foo', 'bar'])

    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, LoadError)
    assert result.exception.reason == LoadErrorReason.CONFLICTING_JUNCTION


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_missing(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')

    result = cli.run(project=project, args=['build', 'missing.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, LoadError)
    assert result.exception.reason == LoadErrorReason.MISSING_FILE


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_with_deps(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')
    copy_subprojects(project, datafiles, ['base'])

    result = cli.run(project=project, args=['build', 'junction-with-deps.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, ElementError)
    assert result.exception.reason == 'element-forbidden-depends'


@pytest.mark.datafiles(DATA_DIR)
def test_invalid_junction_dep(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')
    copy_subprojects(project, datafiles, ['base'])

    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, LoadError)
    assert result.exception.reason == LoadErrorReason.INVALID_DATA


@pytest.mark.datafiles(DATA_DIR)
def test_options_default(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options-default')
    copy_subprojects(project, datafiles, ['options-base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    assert(os.path.exists(os.path.join(checkoutdir, 'pony.txt')))
    assert(not os.path.exists(os.path.join(checkoutdir, 'horsy.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_options(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options')
    copy_subprojects(project, datafiles, ['options-base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    assert(not os.path.exists(os.path.join(checkoutdir, 'pony.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'horsy.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_options_inherit(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options-inherit')
    copy_subprojects(project, datafiles, ['options-base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    assert(not os.path.exists(os.path.join(checkoutdir, 'pony.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'horsy.txt')))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_git_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), 'base'))

    # Write out junction element with git source
    element = {
        'kind': 'junction',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'base.bst'))

    # Verify that bst show does not implicitly fetch subproject
    result = cli.run(project=project, args=['show', 'target.bst'])
    assert result.exit_code != 0
    assert result.exception
    assert isinstance(result.exception, LoadError)
    assert result.exception.reason == LoadErrorReason.SUBPROJECT_FETCH_NEEDED

    # Explicitly fetch subproject
    result = cli.run(project=project, args=['fetch', 'base.bst'])
    assert result.exit_code == 0

    # Check that bst show succeeds now and the pipeline includes the subproject element
    element_list = cli.get_pipeline(project, ['target.bst'])
    assert 'base.bst:target.bst' in element_list


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_git_build(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), 'base'))

    # Write out junction element with git source
    element = {
        'kind': 'junction',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'base.bst'))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected files from both projects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'foo.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_cross_junction_names(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    copy_subprojects(project, datafiles, ['base'])

    element_list = cli.get_pipeline(project, ['base.bst:target.bst'])
    assert 'base.bst:target.bst' in element_list


@pytest.mark.datafiles(DATA_DIR)
def test_build_git_cross_junction_names(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the repo from 'base' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), 'base'))

    # Write out junction element with git source
    element = {
        'kind': 'junction',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'base.bst'))

    print(element)
    print(cli.get_pipeline(project, ['base.bst']))

    # Build (with implicit fetch of subproject), checkout
    result = cli.run(project=project, args=['build', 'base.bst:target.bst'])
    assert result.exit_code == 0
    result = cli.run(project=project, args=['checkout', 'base.bst:target.bst', checkoutdir])
    assert result.exit_code == 0

    # Check that the checkout contains the expected files from both projects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
