import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS, generate_junction
from buildstream import _yaml


def generate_element(repo, element_path, dep_name=None):
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config()
        ]
    }
    if dep_name:
        element['depends'] = [dep_name]

    _yaml.dump(element, element_path)


def generate_import_element(tmpdir, kind, project, name):
    element_name = 'import-{}.bst'.format(name)
    repo_element_path = os.path.join(project, 'elements', element_name)
    files = str(tmpdir.join("imported_files_{}".format(name)))
    os.makedirs(files)

    with open(os.path.join(files, '{}.txt'.format(name)), 'w') as f:
        f.write(name)

    subproject_path = os.path.join(str(tmpdir.join('sub-project-{}'.format(name))))

    repo = create_repo(kind, str(tmpdir.join('element_{}_repo'.format(name))))
    ref = repo.create(files)

    generate_element(repo, repo_element_path)

    return element_name


def generate_project(tmpdir, name, config={}):
    project_name = 'project-{}'.format(name)
    subproject_path = os.path.join(str(tmpdir.join(project_name)))
    os.makedirs(os.path.join(subproject_path, 'elements'))

    project_conf = {
        'name': name,
        'element-path': 'elements'
    }
    project_conf.update(config)
    _yaml.dump(project_conf, os.path.join(subproject_path, 'project.conf'))

    return project_name, subproject_path


def generate_simple_stack(project, name, dependencies):
    element_name = '{}.bst'.format(name)
    element_path = os.path.join(project, 'elements', element_name)
    element = {
        'kind': 'stack',
        'depends': dependencies
    }
    _yaml.dump(element, element_path)

    return element_name


def generate_cross_element(project, subproject_name, import_name):
    basename, _ = os.path.splitext(import_name)
    return generate_simple_stack(project, 'import-{}-{}'.format(subproject_name, basename),
                                 [{
                                     'junction': '{}.bst'.format(subproject_name),
                                     'filename': import_name
                                 }])


@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_cross_junction_multiple_projects(cli, tmpdir, datafiles, kind):
    tmpdir = tmpdir.join(kind)

    # Generate 3 projects: main, a, b
    _, project = generate_project(tmpdir, 'main', {'ref-storage': 'project.refs'})
    project_a, project_a_path = generate_project(tmpdir, 'a')
    project_b, project_b_path = generate_project(tmpdir, 'b')

    # Generate an element with a trackable source for each project
    element_a = generate_import_element(tmpdir, kind, project_a_path, 'a')
    element_b = generate_import_element(tmpdir, kind, project_b_path, 'b')
    element_c = generate_import_element(tmpdir, kind, project, 'c')

    # Create some indirections to the elements with dependencies to test --deps
    stack_a = generate_simple_stack(project_a_path, 'stack-a', [element_a])
    stack_b = generate_simple_stack(project_b_path, 'stack-b', [element_b])

    # Create junctions for projects a and b in main.
    junction_a = '{}.bst'.format(project_a)
    junction_a_path = os.path.join(project, 'elements', junction_a)
    generate_junction(tmpdir.join('repo_a'), project_a_path, junction_a_path, store_ref=False)

    junction_b = '{}.bst'.format(project_b)
    junction_b_path = os.path.join(project, 'elements', junction_b)
    generate_junction(tmpdir.join('repo_b'), project_b_path, junction_b_path, store_ref=False)

    # Track the junctions.
    result = cli.run(project=project, args=['track', junction_a, junction_b])
    result.assert_success()

    # Import elements from a and b in to main.
    imported_a = generate_cross_element(project, project_a, stack_a)
    imported_b = generate_cross_element(project, project_b, stack_b)

    # Generate a top level stack depending on everything
    all_bst = generate_simple_stack(project, 'all', [imported_a, imported_b, element_c])

    # Track without following junctions. But explicitly also track the elements in project a.
    result = cli.run(project=project, args=['track', '--deps', 'all', all_bst, '{}:{}'.format(junction_a, stack_a)])
    result.assert_success()

    # Elements in project b should not be tracked. But elements in project a and main should.
    expected = [element_c,
                '{}:{}'.format(junction_a, element_a)]
    assert set(result.get_tracked_elements()) == set(expected)


@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track_exceptions(cli, tmpdir, datafiles, kind):
    tmpdir = tmpdir.join(kind)

    _, project = generate_project(tmpdir, 'main', {'ref-storage': 'project.refs'})
    project_a, project_a_path = generate_project(tmpdir, 'a')

    element_a = generate_import_element(tmpdir, kind, project_a_path, 'a')
    element_b = generate_import_element(tmpdir, kind, project_a_path, 'b')

    all_bst = generate_simple_stack(project_a_path, 'all', [element_a,
                                                            element_b])

    junction_a = '{}.bst'.format(project_a)
    junction_a_path = os.path.join(project, 'elements', junction_a)
    generate_junction(tmpdir.join('repo_a'), project_a_path, junction_a_path, store_ref=False)

    result = cli.run(project=project, args=['track', junction_a])
    result.assert_success()

    imported_b = generate_cross_element(project, project_a, element_b)
    indirection = generate_simple_stack(project, 'indirection', [imported_b])

    result = cli.run(project=project,
                     args=['track', '--deps', 'all',
                           '--except', indirection,
                           '{}:{}'.format(junction_a, all_bst), imported_b])
    result.assert_success()

    expected = ['{}:{}'.format(junction_a, element_a),
                '{}:{}'.format(junction_a, element_b)]
    assert set(result.get_tracked_elements()) == set(expected)
