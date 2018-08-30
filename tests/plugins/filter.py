import os
import pytest
import shutil
from tests.testutils import cli, create_repo, ALL_REPO_KINDS
from buildstream._exceptions import ErrorDomain
from buildstream import _yaml

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
    assert not os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_include_dynamic(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'output-dynamic-include.bst'])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, 'checkout')
    result = cli.run(project=project, args=['checkout', 'output-dynamic-include.bst', checkout])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout, "foo"))
    assert not os.path.exists(os.path.join(checkout, "bar"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_exclude(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    result = cli.run(project=project, args=['build', 'output-exclude.bst'])
    result.assert_success()

    checkout = os.path.join(tmpdir.dirname, tmpdir.basename, 'checkout')
    result = cli.run(project=project, args=['checkout', 'output-exclude.bst', checkout])
    result.assert_success()
    assert not os.path.exists(os.path.join(checkout, "foo"))
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


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_workspace_open(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    workspace_dir = os.path.join(tmpdir.dirname, tmpdir.basename, "workspace")
    result = cli.run(project=project, args=['workspace', 'open', 'deps-permitted.bst', workspace_dir])
    result.assert_success()
    assert os.path.exists(os.path.join(workspace_dir, "foo"))
    assert os.path.exists(os.path.join(workspace_dir, "bar"))
    assert os.path.exists(os.path.join(workspace_dir, "baz"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_workspace_build(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    tempdir = os.path.join(tmpdir.dirname, tmpdir.basename)
    workspace_dir = os.path.join(tempdir, "workspace")
    result = cli.run(project=project, args=['workspace', 'open', 'output-orphans.bst', workspace_dir])
    result.assert_success()
    src = os.path.join(workspace_dir, "foo")
    dst = os.path.join(workspace_dir, "quux")
    shutil.copyfile(src, dst)
    result = cli.run(project=project, args=['build', 'output-orphans.bst'])
    result.assert_success()
    checkout_dir = os.path.join(tempdir, "checkout")
    result = cli.run(project=project, args=['checkout', 'output-orphans.bst', checkout_dir])
    result.assert_success()
    assert os.path.exists(os.path.join(checkout_dir, "quux"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_workspace_close(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    tempdir = os.path.join(tmpdir.dirname, tmpdir.basename)
    workspace_dir = os.path.join(tempdir, "workspace")
    result = cli.run(project=project, args=['workspace', 'open', 'output-orphans.bst', workspace_dir])
    result.assert_success()
    src = os.path.join(workspace_dir, "foo")
    dst = os.path.join(workspace_dir, "quux")
    shutil.copyfile(src, dst)
    result = cli.run(project=project, args=['workspace', 'close', 'deps-permitted.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'output-orphans.bst'])
    result.assert_success()
    checkout_dir = os.path.join(tempdir, "checkout")
    result = cli.run(project=project, args=['checkout', 'output-orphans.bst', checkout_dir])
    result.assert_success()
    assert not os.path.exists(os.path.join(checkout_dir, "quux"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_workspace_reset(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    tempdir = os.path.join(tmpdir.dirname, tmpdir.basename)
    workspace_dir = os.path.join(tempdir, "workspace")
    result = cli.run(project=project, args=['workspace', 'open', 'output-orphans.bst', workspace_dir])
    result.assert_success()
    src = os.path.join(workspace_dir, "foo")
    dst = os.path.join(workspace_dir, "quux")
    shutil.copyfile(src, dst)
    result = cli.run(project=project, args=['workspace', 'reset', 'deps-permitted.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'output-orphans.bst'])
    result.assert_success()
    checkout_dir = os.path.join(tempdir, "checkout")
    result = cli.run(project=project, args=['checkout', 'output-orphans.bst', checkout_dir])
    result.assert_success()
    assert not os.path.exists(os.path.join(checkout_dir, "quux"))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_track(datafiles, cli, tmpdir):
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"

    project_config = {
        "name": "filter-track-test",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.dump(input_config, input_file)

    filter1_config = {
        "kind": "filter",
        "depends": [
            {"filename": input_name, "type": "build"}
        ]
    }
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.dump(filter1_config, filter1_file)

    filter2_config = {
        "kind": "filter",
        "depends": [
            {"filename": "filter1.bst", "type": "build"}
        ]
    }
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == 'no reference'

    # Now try to track it
    result = cli.run(project=project, args=["track", "filter2.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file)
    assert new_input["sources"][0]["ref"] == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_track_excepted(datafiles, cli, tmpdir):
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"

    project_config = {
        "name": "filter-track-test",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.dump(input_config, input_file)

    filter1_config = {
        "kind": "filter",
        "depends": [
            {"filename": input_name, "type": "build"}
        ]
    }
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.dump(filter1_config, filter1_file)

    filter2_config = {
        "kind": "filter",
        "depends": [
            {"filename": "filter1.bst", "type": "build"}
        ]
    }
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == 'no reference'

    # Now try to track it
    result = cli.run(project=project, args=["track", "filter2.bst", "--except", "input.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file)
    assert "ref" not in new_input["sources"][0]


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_track_multi_to_one(datafiles, cli, tmpdir):
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"

    project_config = {
        "name": "filter-track-test",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.dump(input_config, input_file)

    filter1_config = {
        "kind": "filter",
        "depends": [
            {"filename": input_name, "type": "build"}
        ]
    }
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.dump(filter1_config, filter1_file)

    filter2_config = {
        "kind": "filter",
        "depends": [
            {"filename": input_name, "type": "build"}
        ]
    }
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == 'no reference'

    # Now try to track it
    result = cli.run(project=project, args=["track", "filter1.bst", "filter2.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file)
    assert new_input["sources"][0]["ref"] == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_track_multi(datafiles, cli, tmpdir):
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"
    input2_name = "input2.bst"

    project_config = {
        "name": "filter-track-test",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.dump(input_config, input_file)

    input2_config = dict(input_config)
    input2_file = os.path.join(elements_dir, input2_name)
    _yaml.dump(input2_config, input2_file)

    filter1_config = {
        "kind": "filter",
        "depends": [
            {"filename": input_name, "type": "build"}
        ]
    }
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.dump(filter1_config, filter1_file)

    filter2_config = {
        "kind": "filter",
        "depends": [
            {"filename": input2_name, "type": "build"}
        ]
    }
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == 'no reference'
    assert cli.get_element_state(project, input2_name) == 'no reference'

    # Now try to track it
    result = cli.run(project=project, args=["track", "filter1.bst", "filter2.bst"])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file)
    assert new_input["sources"][0]["ref"] == ref
    new_input2 = _yaml.load(input2_file)
    assert new_input2["sources"][0]["ref"] == ref


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_filter_track_multi_exclude(datafiles, cli, tmpdir):
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(str(datafiles), "files"))
    elements_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    input_name = "input.bst"
    input2_name = "input2.bst"

    project_config = {
        "name": "filter-track-test",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.dump(project_config, project_file)

    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }

    input_file = os.path.join(elements_dir, input_name)
    _yaml.dump(input_config, input_file)

    input2_config = dict(input_config)
    input2_file = os.path.join(elements_dir, input2_name)
    _yaml.dump(input2_config, input2_file)

    filter1_config = {
        "kind": "filter",
        "depends": [
            {"filename": input_name, "type": "build"}
        ]
    }
    filter1_file = os.path.join(elements_dir, "filter1.bst")
    _yaml.dump(filter1_config, filter1_file)

    filter2_config = {
        "kind": "filter",
        "depends": [
            {"filename": input2_name, "type": "build"}
        ]
    }
    filter2_file = os.path.join(elements_dir, "filter2.bst")
    _yaml.dump(filter2_config, filter2_file)

    # Assert that a fetch is needed
    assert cli.get_element_state(project, input_name) == 'no reference'
    assert cli.get_element_state(project, input2_name) == 'no reference'

    # Now try to track it
    result = cli.run(project=project, args=["track", "filter1.bst", "filter2.bst", "--except", input_name])
    result.assert_success()

    # Now check that a ref field exists
    new_input = _yaml.load(input_file)
    assert "ref" not in new_input["sources"][0]
    new_input2 = _yaml.load(input2_file)
    assert new_input2["sources"][0]["ref"] == ref
