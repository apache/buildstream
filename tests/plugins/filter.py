import os
import pytest
from tests.testutils.runcli import cli
from buildstream._exceptions import ErrorDomain

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'filter',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_include(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'output-include.bst'])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, 'checkout')
    result = cli.run(project=project, args=['checkout', 'output-include.bst', checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "foo"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_exclude(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'output-exclude.bst'])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, 'checkout')
    result = cli.run(project=project, args=['checkout', 'output-exclude.bst', checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_orphans(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'output-orphans.bst'])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, 'checkout')
    result = cli.run(project=project, args=['checkout', 'output-orphans.bst', checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "baz"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_deps_ok(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'deps-permitted.bst'])
    result.assert_success()

    result = cli.run(project=project,
                     args=['show', '--deps=run', "--format='%{name}'", 'deps-permitted.bst'])
    result.assert_success()

    assert 'output-exclude.bst' in result.output
    assert 'output-orphans.bst' in result.output


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_forbid_sources(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'forbidden-source.bst'])
    result.assert_main_error(ErrorDomain.ELEMENT, 'element-forbidden-sources')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_forbid_multi_bdep(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'forbidden-multi-bdep.bst'])
    result.assert_main_error(ErrorDomain.ELEMENT, 'filter-bdepend-wrong-count')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_forbid_no_bdep(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'forbidden-no-bdep.bst'])
    result.assert_main_error(ErrorDomain.ELEMENT, 'filter-bdepend-wrong-count')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_forbid_also_rdep(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'forbidden-also-rdep.bst'])
    result.assert_main_error(ErrorDomain.ELEMENT, 'filter-bdepend-also-rdepend')
