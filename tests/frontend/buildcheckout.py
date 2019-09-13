# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import tarfile
import hashlib
import subprocess
import re

import pytest

from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import IS_WINDOWS
from buildstream import _yaml
from buildstream._exceptions import ErrorDomain, LoadErrorReason
from buildstream import utils

from tests.testutils import generate_junction, create_artifact_share

from . import configure_project

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def strict_args(args, strict):
    if strict != "strict":
        return ['--no-strict', *args]
    return args


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict,hardlinks", [
    ("strict", "copies"),
    ("strict", "hardlinks"),
    ("non-strict", "copies"),
    ("non-strict", "hardlinks"),
])
def test_build_checkout(datafiles, cli, strict, hardlinks):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')

    # First build it
    result = cli.run(project=project, args=strict_args(['build', 'target.bst'], strict))
    result.assert_success()

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Prepare checkout args
    checkout_args = strict_args(['artifact', 'checkout'], strict)
    if hardlinks == "hardlinks":
        checkout_args += ['--hardlinks']
    checkout_args += ['target.bst', '--directory', checkout]

    # Now check it out
    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR + "_world")
def test_build_default_all(datafiles, cli):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=['build'])

    result.assert_success()
    target_dir = os.path.join(cli.directory, DATA_DIR + "_world", "elements")
    output_dir = os.path.join(cli.directory, "logs", "test")

    expected = subprocess.Popen(('ls', target_dir), stdout=subprocess.PIPE)
    expected = subprocess.check_output(("wc", "-w"), stdin=expected.stdout)

    results = subprocess.Popen(('ls', output_dir), stdout=subprocess.PIPE)
    results = subprocess.check_output(("wc", "-w"), stdin=results.stdout)

    assert results == expected


@pytest.mark.datafiles(DATA_DIR + "_default")
def test_build_default(cli, datafiles):
    project = str(datafiles)
    result = cli.run(project=project, silent=True, args=['build'])

    result.assert_success()
    results = cli.get_element_state(project, "target2.bst")
    expected = "cached"
    assert results == expected


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict,hardlinks", [
    ("non-strict", "hardlinks"),
])
def test_build_invalid_suffix(datafiles, cli, strict, hardlinks):
    project = str(datafiles)

    result = cli.run(project=project, args=strict_args(['build', 'target.foo'], strict))
    result.assert_main_error(ErrorDomain.LOAD, "bad-element-suffix")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict,hardlinks", [
    ("non-strict", "hardlinks"),
])
def test_build_invalid_suffix_dep(datafiles, cli, strict, hardlinks):
    project = str(datafiles)

    # target2.bst depends on an element called target.foo
    result = cli.run(project=project, args=strict_args(['build', 'target2.bst'], strict))
    result.assert_main_error(ErrorDomain.LOAD, "bad-element-suffix")


@pytest.mark.skipif(IS_WINDOWS, reason='Not available on Windows')
@pytest.mark.datafiles(DATA_DIR)
def test_build_invalid_filename_chars(datafiles, cli):
    project = str(datafiles)
    element_name = 'invalid-chars|<>-in-name.bst'

    # The name of this file contains characters that are not allowed by
    # BuildStream, using it should raise a warning.
    element = {
        'kind': 'stack',
    }
    _yaml.roundtrip_dump(element, os.path.join(project, 'elements', element_name))

    result = cli.run(project=project, args=strict_args(['build', element_name], 'non-strict'))
    result.assert_main_error(ErrorDomain.LOAD, "bad-characters-in-name")


@pytest.mark.skipif(IS_WINDOWS, reason='Not available on Windows')
@pytest.mark.datafiles(DATA_DIR)
def test_build_invalid_filename_chars_dep(datafiles, cli):
    project = str(datafiles)
    element_name = 'invalid-chars|<>-in-name.bst'

    # The name of this file contains characters that are not allowed by
    # BuildStream, and is listed as a dependency of 'invalid-chars-in-dep.bst'.
    # This should also raise a warning.
    element = {
        'kind': 'stack',
    }
    _yaml.roundtrip_dump(element, os.path.join(project, 'elements', element_name))

    result = cli.run(project=project, args=strict_args(['build', 'invalid-chars-in-dep.bst'], 'non-strict'))
    result.assert_main_error(ErrorDomain.LOAD, "bad-characters-in-name")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("deps", [("run"), ("none"), ("build"), ("all")])
def test_build_checkout_deps(datafiles, cli, deps):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')
    element_name = "checkout-deps.bst"

    # First build it
    result = cli.run(project=project, args=['build', element_name])
    result.assert_success()

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Now check it out
    result = cli.run(project=project, args=['artifact', 'checkout', element_name,
                                            '--deps', deps, '--directory', checkout])
    result.assert_success()

    # Verify output of this element
    filename = os.path.join(checkout, 'etc', 'buildstream', 'config')
    if deps == "build":
        assert not os.path.exists(filename)
    else:
        assert os.path.exists(filename)

    # Verify output of this element's build dependencies
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    if deps in ["build", "all"]:
        assert os.path.exists(filename)
    else:
        assert not os.path.exists(filename)

    # Verify output of this element's runtime dependencies
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    if deps in ["run", "all"]:
        assert os.path.exists(filename)
    else:
        assert not os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_unbuilt(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')

    # Check that checking out an unbuilt element fails nicely
    result = cli.run(project=project, args=['artifact', 'checkout', 'target.bst', '--directory', checkout])
    result.assert_main_error(ErrorDomain.STREAM, "uncached-checkout-attempt")


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_compression_no_tar(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    checkout_args = ['artifact', 'checkout', '--directory', checkout, '--compression', 'gz', 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    assert "ERROR: --compression can only be provided if --tar is provided" in result.stderr
    assert result.exit_code != 0

# If we don't support the extension, we default to an uncompressed tarball
@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tar_with_unconventional_name(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.foo')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    checkout_args = ['artifact', 'checkout', '--tar', checkout, 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.open(name=checkout, mode='r')
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tar_with_unsupported_ext(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar.foo')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    checkout_args = ['artifact', 'checkout', '--tar', checkout, 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    assert "Invalid file extension given with '--tar': Expected compression with unknown file extension ('.foo'), " \
           "supported extensions are ('.tar'), ('.gz'), ('.xz'), ('.bz2')" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tar_no_compression(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar.gz')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--tar', checkout, 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.open(name=checkout, mode='r:gz')
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--tar', checkout, 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.TarFile(checkout)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_using_ref(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')

    result = cli.run(project=project, args=['build', 'checkout-deps.bst'])
    result.assert_success()

    key = cli.get_element_key(project, 'checkout-deps.bst')
    checkout_args = ['artifact', 'checkout', '--directory', checkout, '--deps', 'none', 'test/checkout-deps/' + key]

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    filename = os.path.join(checkout, 'etc', 'buildstream', 'config')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball_using_ref(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar')

    result = cli.run(project=project, args=['build', 'checkout-deps.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    key = cli.get_element_key(project, 'checkout-deps.bst')
    checkout_args = ['artifact', 'checkout', '--deps', 'none', '--tar', checkout, 'test/checkout-deps/' + key]

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.TarFile(checkout)
    assert os.path.join('.', 'etc', 'buildstream', 'config') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_build_deps_using_ref(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')

    result = cli.run(project=project, args=['build', 'checkout-deps.bst'])
    result.assert_success()

    key = cli.get_element_key(project, 'checkout-deps.bst')
    checkout_args = ['artifact', 'checkout', '--directory', checkout, '--deps', 'build', 'test/checkout-deps/' + key]

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    build_dep_files = os.path.join(checkout, 'usr', 'include', 'pony.h')
    runtime_dep_files = os.path.join(checkout, 'usr', 'bin', 'hello')
    target_files = os.path.join(checkout, 'etc', 'buildstream', 'config')
    assert os.path.exists(build_dep_files)
    assert not os.path.exists(runtime_dep_files)
    assert not os.path.exists(target_files)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_runtime_deps_using_ref_fails(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')

    result = cli.run(project=project, args=['build', 'checkout-deps.bst'])
    result.assert_success()

    key = cli.get_element_key(project, 'checkout-deps.bst')
    checkout_args = ['artifact', 'checkout', '--directory', checkout, '--deps', 'run', 'test/checkout-deps/' + key]

    result = cli.run(project=project, args=checkout_args)
    result.assert_main_error(ErrorDomain.STREAM, None)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_invalid_ref(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar')

    result = cli.run(project=project, args=['build', 'checkout-deps.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    non_existent_artifact = 'test/checkout-deps/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    checkout_args = ['artifact', 'checkout', '--deps', 'none', '--tar', checkout, non_existent_artifact]
    result = cli.run(project=project, args=checkout_args)

    assert "Error while staging dependencies into a sandbox: 'No artifacts to stage'" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_no_tar_no_directory(datafiles, cli, tmpdir):
    project = str(datafiles)
    runtestdir = str(tmpdir)

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    checkout_args = ['artifact', 'checkout', 'target.bst']

    result = cli.run(cwd=runtestdir, project=project, args=checkout_args)
    result.assert_success()
    filename = os.path.join(runtestdir, 'target', 'usr', 'bin', 'hello')
    assert os.path.exists(filename)
    filename = os.path.join(runtestdir, 'target', 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("compression", [("gz"), ("xz"), ("bz2")])
def test_build_checkout_tarball_compression(datafiles, cli, compression):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--tar', checkout, '--compression', compression, 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    # Docs say not to use TarFile class directly, using .open seems to work.
    # https://docs.python.org/3/library/tarfile.html#tarfile.TarFile
    tar = tarfile.open(name=checkout, mode='r:' + compression)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball_stdout(datafiles, cli):
    project = str(datafiles)
    tarball = os.path.join(cli.directory, 'tarball.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--tar', '-', 'target.bst']

    result = cli.run(project=project, args=checkout_args, binary_capture=True)
    result.assert_success()

    with open(tarball, 'wb') as f:
        f.write(result.output)

    tar = tarfile.TarFile(tarball)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball_mtime_nonzero(datafiles, cli):
    project = str(datafiles)
    tarpath = os.path.join(cli.directory, 'mtime_tar.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    checkout_args = ['artifact', 'checkout', '--tar', tarpath, 'target.bst']
    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.TarFile(tarpath)
    for tarinfo in tar.getmembers():
        # An mtime of zero can be confusing to other software,
        # e.g. ninja build and template toolkit have both taken zero mtime to
        # mean 'file does not exist'.
        assert tarinfo.mtime > 0


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_tarball_is_deterministic(datafiles, cli):
    project = str(datafiles)
    tarball1 = os.path.join(cli.directory, 'tarball1.tar')
    tarball2 = os.path.join(cli.directory, 'tarball2.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--force', 'target.bst']

    checkout_args1 = checkout_args + ['--tar', tarball1]
    result = cli.run(project=project, args=checkout_args1)
    result.assert_success()

    checkout_args2 = checkout_args + ['--tar', tarball2]
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
def test_build_checkout_tarball_links(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout.tar')
    extract = os.path.join(cli.directory, 'extract')

    result = cli.run(project=project, args=['build', 'import-links.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--tar', checkout, 'import-links.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.open(name=checkout, mode="r:")
    tar.extractall(extract)
    assert open(os.path.join(extract, 'basicfolder', 'basicsymlink')).read() == "file contents\n"


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_links(datafiles, cli):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, 'checkout')

    result = cli.run(project=project, args=['build', 'import-links.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    checkout_args = ['artifact', 'checkout', '--directory', checkout, 'import-links.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    assert open(os.path.join(checkout, 'basicfolder', 'basicsymlink')).read() == "file contents\n"


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("hardlinks", [("copies"), ("hardlinks")])
def test_build_checkout_nonempty(datafiles, cli, hardlinks):
    project = str(datafiles)
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
    checkout_args = ['artifact', 'checkout']
    if hardlinks == "hardlinks":
        checkout_args += ['--hardlinks']
    checkout_args += ['target.bst', '--directory', checkout]

    # Now check it out
    result = cli.run(project=project, args=checkout_args)
    result.assert_main_error(ErrorDomain.STREAM, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("hardlinks", [("copies"), ("hardlinks")])
def test_build_checkout_force(datafiles, cli, hardlinks):
    project = str(datafiles)
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
    checkout_args = ['artifact', 'checkout', '--force']
    if hardlinks == "hardlinks":
        checkout_args += ['--hardlinks']
    checkout_args += ['target.bst', '--directory', checkout]

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
    project = str(datafiles)
    tarball = os.path.join(cli.directory, 'tarball.tar')

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    with open(tarball, "w") as f:
        f.write("Hello")

    checkout_args = ['artifact', 'checkout', '--force', '--tar', tarball, 'target.bst']

    result = cli.run(project=project, args=checkout_args)
    result.assert_success()

    tar = tarfile.TarFile(tarball)
    assert os.path.join('.', 'usr', 'bin', 'hello') in tar.getnames()
    assert os.path.join('.', 'usr', 'include', 'pony.h') in tar.getnames()


@pytest.mark.datafiles(DATA_DIR)
def test_install_to_build(cli, datafiles):
    project = str(datafiles)
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
    _yaml.roundtrip_dump(element, element_path)

    # Now try to track it, this will bail with the appropriate error
    # informing the user to track the junction first
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.SUBPROJECT_INCONSISTENT)

    # Assert that we have the expected provenance encoded into the error
    element_node = _yaml.load(element_path, shortname='junction-dep.bst')
    ref_node = element_node.get_sequence('depends').mapping_at(0)
    provenance = ref_node.get_provenance()
    assert str(provenance) in result.stderr


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
    _yaml.roundtrip_dump(element, element_path)

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
        _yaml.roundtrip_dump(project_refs, os.path.join(project, 'junction.refs'))

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout_junction(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

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
    _yaml.roundtrip_dump(element, element_path)

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'artifact', 'checkout', 'junction-dep.bst', '--directory', checkout
    ])
    result.assert_success()

    # Assert the content of /etc/animal.conf
    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)
    with open(filename, 'r') as f:
        contents = f.read()
    assert contents == 'animal=Pony\n'


# Test that default targets work with projects with junctions
@pytest.mark.datafiles(DATA_DIR + "_world")
def test_build_checkout_junction_default_targets(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

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
    _yaml.roundtrip_dump(element, element_path)

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'artifact', 'checkout', 'junction-dep.bst', '--directory', checkout
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
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    workspace = os.path.join(cli.directory, 'workspace')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

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
    _yaml.roundtrip_dump(element, element_path)

    # Now open a workspace on the junction
    #
    result = cli.run(project=project, args=['workspace', 'open', '--directory', workspace, 'junction.bst'])
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
        'artifact', 'checkout', 'junction-dep.bst', '--directory', checkout
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
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    generate_junction(tmpdir, subproject_path, junction_path)

    result = cli.run(project=project, args=['build', 'junction.bst:import-etc.bst'])
    result.assert_success()

    result = cli.run(project=project, args=['artifact', 'checkout', 'junction.bst:import-etc.bst',
                                            '--directory', checkout])
    result.assert_success()

    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_build_junction_short_notation(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

    # Create a stack element to depend on a cross junction element, using
    # colon (:) as the separator
    element = {
        'kind': 'stack',
        'depends': ['junction.bst:import-etc.bst']
    }
    _yaml.roundtrip_dump(element, element_path)

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'artifact', 'checkout', 'junction-dep.bst', '--directory', checkout
    ])
    result.assert_success()

    # Assert the content of /etc/animal.conf
    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)
    with open(filename, 'r') as f:
        contents = f.read()
    assert contents == 'animal=Pony\n'


@pytest.mark.datafiles(DATA_DIR)
def test_build_junction_short_notation_filename(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')
    checkout = os.path.join(cli.directory, 'checkout')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

    # Create a stack element to depend on a cross junction element, using
    # colon (:) as the separator
    element = {
        'kind': 'stack',
        'depends': [{'filename': 'junction.bst:import-etc.bst'}]
    }
    _yaml.roundtrip_dump(element, element_path)

    # Now try to build it, this should automatically result in fetching
    # the junction itself at load time.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_success()

    # Assert that it's cached now
    assert cli.get_element_state(project, 'junction-dep.bst') == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'artifact', 'checkout', 'junction-dep.bst', '--directory', checkout
    ])
    result.assert_success()

    # Assert the content of /etc/animal.conf
    filename = os.path.join(checkout, 'etc', 'animal.conf')
    assert os.path.exists(filename)
    with open(filename, 'r') as f:
        contents = f.read()
    assert contents == 'animal=Pony\n'


@pytest.mark.datafiles(DATA_DIR)
def test_build_junction_short_notation_with_junction(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

    # Create a stack element to depend on a cross junction element, using
    # colon (:) as the separator
    element = {
        'kind': 'stack',
        'depends': [{
            'filename': 'junction.bst:import-etc.bst',
            'junction': 'junction.bst',
        }]
    }
    _yaml.roundtrip_dump(element, element_path)

    # Now try to build it, this should fail as filenames should not contain
    # `:` when junction is explicity specified
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


@pytest.mark.datafiles(DATA_DIR)
def test_build_junction_transitive_short_notation_with_junction(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, 'files', 'sub-project')
    junction_path = os.path.join(project, 'elements', 'junction.bst')
    element_path = os.path.join(project, 'elements', 'junction-dep.bst')

    # Create a repo to hold the subproject and generate a junction element for it
    generate_junction(tmpdir, subproject_path, junction_path)

    # Create a stack element to depend on a cross junction element, using
    # colon (:) as the separator
    element = {
        'kind': 'stack',
        'depends': ['junction.bst:import-etc.bst:foo.bst']
    }
    _yaml.roundtrip_dump(element, element_path)

    # Now try to build it, this should fail as recursive lookups for
    # cross-junction elements is not allowed.
    result = cli.run(project=project, args=['build', 'junction-dep.bst'])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


# Should check that after a build we have partial artifacts locally, but should
# then attempt to fetch them when doing a artifact checkout
@pytest.mark.datafiles(DATA_DIR)
def test_partial_artifact_checkout_fetch(cli, datafiles, tmpdir):
    project = str(datafiles)
    build_elt = 'import-bin.bst'
    checkout_dir = os.path.join(str(tmpdir), 'checkout')

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        cli.configure({'artifacts': {
            'url': share.repo,
            'push': True
        }})

        result = cli.run(project=project, args=['build', build_elt])
        result.assert_success()

        # A push artifact cache means we have to pull to push to them, so
        # delete some blobs from that CAS such that we have to fetch
        digest = utils.sha256sum(os.path.join(project, 'files', 'bin-files', 'usr', 'bin', 'hello'))
        objpath = os.path.join(cli.directory, 'cas', 'objects', digest[:2], digest[2:])
        os.unlink(objpath)

        # Verify that the build-only dependency is not (complete) in the local cache
        result = cli.run(project=project, args=[
            'artifact', 'checkout', build_elt,
            '--directory', checkout_dir])
        result.assert_main_error(ErrorDomain.STREAM, 'uncached-checkout-attempt')

        # Verify that the pull method fetches relevant artifacts in order to stage
        result = cli.run(project=project, args=[
            'artifact', 'checkout', '--pull', build_elt,
            '--directory', checkout_dir])
        result.assert_success()

        # should have pulled whatever was deleted previous
        assert 'import-bin.bst' in result.get_pulled_elements()


@pytest.mark.datafiles(DATA_DIR)
def test_partial_checkout_fail(tmpdir, datafiles, cli):
    project = str(datafiles)
    build_elt = 'import-bin.bst'
    checkout_dir = os.path.join(str(tmpdir), 'checkout')

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare')) as share:

        cli.configure({'artifacts': {
            'url': share.repo,
            'push': True
        }})

        res = cli.run(project=project, args=[
            'artifact', 'checkout', '--pull', build_elt, '--directory',
            checkout_dir])
        res.assert_main_error(ErrorDomain.STREAM, 'uncached-checkout-attempt')
        assert re.findall(r'Remote \((\S+)\) does not have artifact (\S+) cached', res.stderr)
