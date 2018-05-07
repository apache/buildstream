import os
from tests.testutils import cli, create_repo
from buildstream import _yaml


def prepare_junction_project(cli, tmpdir):
    main_project = tmpdir.join("main")
    sub_project = tmpdir.join("sub")
    os.makedirs(str(main_project))
    os.makedirs(str(sub_project))

    _yaml.dump({'name': 'main'}, str(main_project.join("project.conf")))
    _yaml.dump({'name': 'sub'}, str(sub_project.join("project.conf")))

    import_dir = tmpdir.join("import")
    os.makedirs(str(import_dir))
    with open(str(import_dir.join("hello.txt")), "w") as f:
        f.write("hello!")

    import_repo_dir = tmpdir.join("import_repo")
    os.makedirs(str(import_repo_dir))
    import_repo = create_repo("git", str(import_repo_dir))
    import_ref = import_repo.create(str(import_dir))

    _yaml.dump({'kind': 'import',
                'sources': [import_repo.source_config(ref=import_ref)]},
               str(sub_project.join("data.bst")))

    sub_repo_dir = tmpdir.join("sub_repo")
    os.makedirs(str(sub_repo_dir))
    sub_repo = create_repo("git", str(sub_repo_dir))
    sub_ref = sub_repo.create(str(sub_project))

    _yaml.dump({'kind': 'junction',
                'sources': [sub_repo.source_config(ref=sub_ref)]},
               str(main_project.join("sub.bst")))

    args = ['fetch', 'sub.bst']
    result = cli.run(project=str(main_project), args=args)
    result.assert_success()

    return str(main_project)


def open_cross_junction(cli, tmpdir):
    project = prepare_junction_project(cli, tmpdir)
    workspace = tmpdir.join("workspace")

    element = 'sub.bst:data.bst'
    args = ['workspace', 'open', element, str(workspace)]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert cli.get_element_state(project, element) == 'buildable'
    assert os.path.exists(str(workspace.join('hello.txt')))

    return project, workspace


def test_open_cross_junction(cli, tmpdir):
    open_cross_junction(cli, tmpdir)


def test_list_cross_junction(cli, tmpdir):
    project, workspace = open_cross_junction(cli, tmpdir)

    element = 'sub.bst:data.bst'

    args = ['workspace', 'list']
    result = cli.run(project=project, args=args)
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    assert isinstance(loaded.get('workspaces'), list)
    workspaces = loaded['workspaces']
    assert len(workspaces) == 1
    assert 'element' in workspaces[0]
    assert workspaces[0]['element'] == element


def test_close_cross_junction(cli, tmpdir):
    project, workspace = open_cross_junction(cli, tmpdir)

    element = 'sub.bst:data.bst'
    args = ['workspace', 'close', '--remove-dir', element]
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert not os.path.exists(str(workspace))

    args = ['workspace', 'list']
    result = cli.run(project=project, args=args)
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    assert isinstance(loaded.get('workspaces'), list)
    workspaces = loaded['workspaces']
    assert len(workspaces) == 0


def test_close_all_cross_junction(cli, tmpdir):
    project, workspace = open_cross_junction(cli, tmpdir)

    args = ['workspace', 'close', '--remove-dir', '--all']
    result = cli.run(project=project, args=args)
    result.assert_success()

    assert not os.path.exists(str(workspace))

    args = ['workspace', 'list']
    result = cli.run(project=project, args=args)
    result.assert_success()

    loaded = _yaml.load_data(result.output)
    assert isinstance(loaded.get('workspaces'), list)
    workspaces = loaded['workspaces']
    assert len(workspaces) == 0
