import os
import pytest
import shutil

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream.plugintestutils import cli
from tests.testutils import create_repo
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
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'foo.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_build_of_same_junction_used_twice(cli, datafiles):
    project = os.path.join(str(datafiles), 'inconsistent-names')

    # Check we can build a project that contains the same junction
    # that is used twice, but named differently
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_missing_file_in_subproject(cli, datafiles):
    project = os.path.join(str(datafiles), 'missing-element')
    result = cli.run(project=project, args=['show', 'target.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "target.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_missing_file_in_subsubproject(cli, datafiles):
    project = os.path.join(str(datafiles), 'missing-element')
    result = cli.run(project=project, args=['show', 'sub-target.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "junction-A.bst:target.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_missing_junction_in_subproject(cli, datafiles):
    project = os.path.join(str(datafiles), 'missing-element')
    result = cli.run(project=project, args=['show', 'sub-target-bad-junction.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)

    # Assert that we have the expected provenance encoded into the error
    assert "junction-A.bst:bad-junction-target.bst [line 4 column 2]" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_nested_simple(cli, tmpdir, datafiles):
    foo = os.path.join(str(datafiles), 'foo')
    copy_subprojects(foo, datafiles, ['base'])

    project = os.path.join(str(datafiles), 'nested')
    copy_subprojects(project, datafiles, ['foo'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

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
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

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
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.CONFLICTING_JUNCTION)


# Test that we error correctly when the junction element itself is missing
@pytest.mark.datafiles(DATA_DIR)
def test_missing_junction(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')

    result = cli.run(project=project, args=['build', 'missing.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


# Test that we error correctly when an element is not found in the subproject
@pytest.mark.datafiles(DATA_DIR)
def test_missing_subproject_element(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')
    copy_subprojects(project, datafiles, ['base'])

    result = cli.run(project=project, args=['build', 'missing-element.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.MISSING_FILE)


# Test that we error correctly when a junction itself has dependencies
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_with_deps(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')
    copy_subprojects(project, datafiles, ['base'])

    result = cli.run(project=project, args=['build', 'junction-with-deps.bst'])
    result.assert_main_error(ErrorDomain.ELEMENT, 'element-forbidden-depends')


# Test that we error correctly when a junction is directly depended on
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_junction_dep(cli, datafiles):
    project = os.path.join(str(datafiles), 'invalid')
    copy_subprojects(project, datafiles, ['base'])

    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_options_default(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options-default')
    copy_subprojects(project, datafiles, ['options-base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

    assert(os.path.exists(os.path.join(checkoutdir, 'pony.txt')))
    assert(not os.path.exists(os.path.join(checkoutdir, 'horsy.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_options(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options')
    copy_subprojects(project, datafiles, ['options-base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

    assert(not os.path.exists(os.path.join(checkoutdir, 'pony.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'horsy.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_options_inherit(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'options-inherit')
    copy_subprojects(project, datafiles, ['options-base'])

    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Build, checkout
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

    assert(not os.path.exists(os.path.join(checkoutdir, 'pony.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'horsy.txt')))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(DATA_DIR)
def test_git_show(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')

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
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_FETCH_NEEDED)

    # Explicitly fetch subproject
    result = cli.run(project=project, args=['source', 'fetch', 'base.bst'])
    result.assert_success()

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
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
    assert(os.path.exists(os.path.join(checkoutdir, 'foo.txt')))


@pytest.mark.datafiles(DATA_DIR)
def test_cross_junction_names(cli, datafiles):
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
    result.assert_success()
    result = cli.run(project=project, args=['artifact', 'checkout', 'base.bst:target.bst', '--directory', checkoutdir])
    result.assert_success()

    # Check that the checkout contains the expected files from both projects
    assert(os.path.exists(os.path.join(checkoutdir, 'base.txt')))
