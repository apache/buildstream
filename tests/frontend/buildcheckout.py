import os
import tarfile
import hashlib
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS, generate_junction

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason

from . import configure_project

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def strict_args(args, strict):
    if strict != "strict":
        return ['--no-strict'] + args
    return args


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict,hardlinks", [
    ("strict", "copies"),
    ("strict", "hardlinks"),
    ("non-strict", "copies"),
    ("non-strict", "hardlinks"),
])
def test_build_checkout(datafiles, cli, strict, hardlinks):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # First build it
    result = cli.run(project=project, args=strict_args(['build', 'target.bst'], strict))
    result.assert_success()

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Prepare checkout args
    checkout_args = strict_args(['checkout'], strict)
    if hardlinks == "hardlinks":
        checkout_args += ['--hardlinks']
    checkout_args += ['target.bst', checkout]

    # Now check it out
    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("deps", [("run"), ("none")])
def test_build_checkout_deps(datafiles, cli, deps):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # First build it
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Now check it out
    result = cli.run(project=project, args=['checkout', 'target.bst', '--deps', deps, checkout])
    result.assert_success()

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')

    if deps == "run":
        assert os.path.exists(filename)
    else:
        assert not os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')

    if deps == "run":
        assert os.path.exists(filename)
    else:
        assert not os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_unbuilt(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # Check that checking out an unbuilt element fails nicely
    result = cli.run(project=project, args=['checkout', 'target.bst', checkout])
    result.assert_main_error(ErrorDomain.STREAM, "uncached-checkout-attempt")


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['checkout', '--tar', 'target.bst', checkout]

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.TarFile(checkout)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.skip(reason="Capturing the binary output is causing a stacktrace")
@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball_stdout(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    tarball = os.path.join(cli.directory, 'tarball.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['checkout', '--tar', 'target.bst', '-']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    with open(tarball, 'wb') as f:
        f.write(result.output)

    tar = tarfile.TarFile(tarball)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball_is_deterministic(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    tarball1 = os.path.join(cli.directory, 'tarball1.tar')
    tarball2 = os.path.join(cli.directory, 'tarball2.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['checkout', '--force', '--tar', 'target.bst']

    checkout_args1 = checkout_args + [tarball1]
    result = cli.run(project=project, args=checkout_args1)
    result.assert_success()

    checkout_args2 = checkout_args + [tarball2]
    result = cli.run(project=project, args=checkout_args2)
    result.assert_success()

    with open(tarball1, 'rb') as f:
        contents = f.read()
    hash1 = hashlib.sha1(contents).hexdigest()

    with open(tarball2, 'rb') as f:
        contents = f.read()
    hash2 = hashlib.sha1(contents).hexdigest()

    assert hash1 == hash2


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("hardlinks", [("copies"), ("hardlinks")])
def test_build_checkout_nonempty(datafiles, cli, hardlinks):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    filename = os.path.join(checkout, "file.txt")

    # First build it
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Create the checkout dir and add a file to it, should cause checkout to fail
    os.makedirs(checkout, exist_ok=True)
    with open(filename, "w") as f:
        f.write("Hello")

    # Prepare checkout args
    checkout_args = ['checkout']
    if hardlinks == "hardlinks":
        checkout_args += ['--hardlinks']
    checkout_args += ['target.bst', checkout]

    # Now check it out
    result = cli.run(project=project, args=checkout_args)
    result.assert_main_error(ErrorDomain.STREAM, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("hardlinks", [("copies"), ("hardlinks")])
def test_build_checkout_force(datafiles, cli, hardlinks):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')
    filename = os.path.join(checkout, "file.txt")

    # First build it
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Create the checkout dir and add a file to it, should cause checkout to fail
    os.makedirs(checkout, exist_ok=True)
    with open(filename, "w") as f:
        f.write("Hello")

    # Prepare checkout args
    checkout_args = ['checkout', '--force']
    if hardlinks == "hardlinks":
        checkout_args += ['--hardlinks']
    checkout_args += ['target.bst', checkout]

    # Now check it out
    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    # Check that the file we added is still there
    filename = os.path.join(checkout, 'file.txt')
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_force_tarball(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    tarball = os.path.join(cli.directory, 'tarball.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    with open(tarball, "w") as f:
        f.write("Hello")

    checkout_args = ['checkout', '--force', '--tar', 'target.bst', tarball]

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.TarFile(tarball)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()

fetch_build_checkout_combos = \
    [("strict", kind) for kind in ALL_REPO_KINDS] + \
    [("non-strict", kind) for kind in ALL_REPO_KINDS]


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict,kind", fetch_build_checkout_combos)
def test_fetch_build_checkout(cli, tmpdir, datafiles, strict, kind):
    checkout = os.path.join(cli.directory, 'checkout')
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'build-test-{}.bst'.format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

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

    assert cli.get_element_state(project, element_name) == 'fetch needed'
    result = cli.run(project=project, args=strict_args(['build', element_name], strict))
    result.assert_success()
    assert cli.get_element_state(project, element_name) == 'cached'

    # Now check it out
    result = cli.run(project=project, args=strict_args([
        'checkout', element_name, checkout
    ], strict))
    result.assert_success()

    # Check that the pony.h include from files/dev-files exists
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_install_to_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element = 'installed-to-build.bst'

    # Attempt building the element
    # We expect this to throw an ElementError, since the element will
    # attempt to stage into /buildstream/build, which is not allowed.
    result = cli.run(project=project, args=strict_args(['build', element], True))

    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.ELEMENT, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_inconsistent_junction(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
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

    # Now try to track it, this will bail with the appropriate error
    # informing the user to track the junction first
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [('inline'), ('project.refs')])
def test_unfetched_junction(cli, tmpdir, datafiles, ref_storage):
    project = os.path.join(datafiles.dirname, datafiles.basename)
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

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_junction(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    ref = generate_junction(tmpdir, subproject_path, junction_path)

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

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'checkout', 'junction-dep.bst', checkout
    ])
    result.assert_success()

    # Assert the content of /etc/animal.conf
    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)
    with open(filename, 'r') as f:
        contents = f.read()
    assert contents == 'animal=Pony\n'


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_workspaced_junction(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    workspace = os.path.join(cli.directory, 'workspace')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    ref = generate_junction(tmpdir, subproject_path, junction_path)

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

    # Now open a workspace on the junction
    #
    result = cli.run(project=project, args=['workspace', 'open', 'junction.bst', workspace])
    result.assert_success()
    filename = os.path.join(workspace, 'files', 'etc-files', 'etc', 'animal.conf')

    # Assert the content of /etc/animal.conf in the workspace
    assert os.path.exists(filename)
    with open(filename, 'r') as f:
        contents = f.read()
    assert contents == 'animal=Pony\n'

    # Modify the content of the animal.conf in the workspace
    with open(filename, 'w') as f:
        f.write('animal=Horsy\n')

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'checkout', 'junction-dep.bst', checkout
    ])
    result.assert_success()

    # Assert the workspace modified content of /etc/animal.conf
    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)
    with open(filename, 'r') as f:
        contents = f.read()
    assert contents == 'animal=Horsy\n'


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_cross_junction(datafiles, cli, tmpdir):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    generate_junction(tmpdir, subproject_path, junction_path)

    result = cli.run(project=project, args=['build', 'junction.bst:import-etc.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['checkout', 'junction.bst:import-etc.bst', checkout])
    result.assert_success()

    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)
