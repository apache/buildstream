#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors: Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#           Jonathan Maw <jonathan.maw@codethink.co.uk>
#           William Salmon <will.salmon@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import subprocess
import shutil

import pytest

from buildstream import Node
from buildstream.exceptions import ErrorDomain
from buildstream.plugin import CoreWarnings
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import generate_project, generate_element, load_yaml
from buildstream.testing import create_repo
from buildstream.testing._utils.site import HAVE_GIT, HAVE_OLD_GIT

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "git",)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_fetch_bad_ref(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Write out our test target with a bad ref
    element = {"kind": "import", "sources": [repo.source_config(ref="5")]}
    generate_element(project, "target.bst", element)

    # Assert that fetch raises an error here
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.skipif(HAVE_OLD_GIT, reason="old git cannot clone a shallow repo to stage the source")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_fetch_shallow(cli, tmpdir, datafiles):
    project = str(datafiles)
    workspacedir = os.path.join(str(tmpdir), "workspace")

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))
    first_commit = repo.latest_commit()
    repo.add_commit()
    repo.add_tag("tag")

    ref = "tag-0-g" + repo.latest_commit()

    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    generate_element(project, "target.bst", element)

    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["workspace", "open", "--directory", workspacedir, "target.bst"])
    result.assert_success()

    assert subprocess.call(["git", "show", "tag"], cwd=workspacedir) == 0
    assert subprocess.call(["git", "show", first_commit], cwd=workspacedir) != 0


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_fetch_checkout(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_recursive_submodule_fetch_checkout(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create a submodule from the 'othersubrepofiles' subdir
    subsubrepo = create_repo("git", str(tmpdir), "subsubrepo")
    subsubrepo.create(os.path.join(project, "othersubrepofiles"))

    # Create another submodule from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Configure submodules
    subrepo.add_submodule("subdir", "file://" + subsubrepo.repo)
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out all files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "subdir", "unicornfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_fetch_source_enable_explicit(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config_extra(ref=ref, checkout_submodules=True)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_fetch_source_disable(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config_extra(ref=ref, checkout_submodules=False)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert not os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_fetch_submodule_does_override(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo, checkout=True)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config_extra(ref=ref, checkout_submodules=False)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_fetch_submodule_individual_checkout(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create another submodule from the 'othersubrepofiles' subdir
    other_subrepo = create_repo("git", str(tmpdir), "othersubrepo")
    other_subrepo.create(os.path.join(project, "othersubrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    repo.add_submodule("subdir", "file://" + subrepo.repo, checkout=False)
    ref = repo.add_submodule("othersubdir", "file://" + other_subrepo.repo)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config_extra(ref=ref, checkout_submodules=True)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert not os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "othersubdir", "unicornfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_fetch_submodule_individual_checkout_explicit(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create another submodule from the 'othersubrepofiles' subdir
    other_subrepo = create_repo("git", str(tmpdir), "othersubrepo")
    other_subrepo.create(os.path.join(project, "othersubrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    repo.add_submodule("subdir", "file://" + subrepo.repo, checkout=False)
    ref = repo.add_submodule("othersubdir", "file://" + other_subrepo.repo, checkout=True)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config_extra(ref=ref, checkout_submodules=True)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert not os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))
    assert os.path.exists(os.path.join(checkoutdir, "othersubdir", "unicornfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "project-override"))
def test_submodule_fetch_project_override(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    generate_element(project, "target.bst", element)

    # Fetch, build, checkout
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, "file.txt"))
    assert not os.path.exists(os.path.join(checkoutdir, "subdir", "ponyfile.txt"))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_track_ignore_inconsistent(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(project, "repofiles"))

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
    generate_element(project, "target.bst", element)

    # Now add a .gitmodules file with an inconsistent submodule,
    # we are calling this inconsistent because the file was created
    # but `git submodule add` was never called, so there is no reference
    # associated to the submodule.
    #
    repo.add_file(os.path.join(project, "inconsistent-submodule", ".gitmodules"))

    # Fetch should work, we're not yet at the offending ref
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()

    # Track will encounter an inconsistent submodule without any ref
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()

    # Assert that we are just fine without it, and emit a warning to the user.
    assert "Ignoring inconsistent submodule" in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_submodule_track_no_ref_or_track(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Write out our test target
    gitsource = repo.source_config(ref=None)
    gitsource.pop("track")
    element = {"kind": "import", "sources": [gitsource]}
    generate_element(project, "target.bst", element)

    # Track will encounter an inconsistent submodule without any ref
    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_main_error(ErrorDomain.SOURCE, "missing-track-and-ref")
    result.assert_task_error(None, None)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("fail", ["warn", "error"])
def test_ref_not_in_track(cli, tmpdir, datafiles, fail):
    project = str(datafiles)

    # Make the warning an error if we're testing errors
    if fail == "error":
        generate_project(project, config={"fatal-warnings": [CoreWarnings.REF_NOT_IN_TRACK]})

    # Create the repo from 'repofiles', create a branch without latest commit
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(project, "repofiles"))

    gitsource = repo.source_config(ref=ref)

    # Overwrite the track value to the added branch
    gitsource["track"] = "foo"

    # Write out our test target
    element = {"kind": "import", "sources": [gitsource]}
    generate_element(project, "target.bst", element)

    result = cli.run(project=project, args=["build", "target.bst"])

    # Assert a warning or an error depending on what we're checking
    if fail == "error":
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, CoreWarnings.REF_NOT_IN_TRACK)
    else:
        result.assert_success()
        assert "ref-not-in-track" in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("fail", ["warn", "error"])
def test_unlisted_submodule(cli, tmpdir, datafiles, fail):
    project = str(datafiles)

    # Make the warning an error if we're testing errors
    if fail == "error":
        generate_project(project, config={"fatal-warnings": ["git:unlisted-submodule"]})

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Create the source, and delete the explicit configuration
    # of the submodules.
    #
    # We expect this to cause an unlisted submodule warning
    # after the source has been fetched.
    #
    gitsource = repo.source_config(ref=ref)
    del gitsource["submodules"]

    # Write out our test target
    element = {"kind": "import", "sources": [gitsource]}
    generate_element(project, "target.bst", element)

    # The warning or error is reported during fetch. There should be no
    # error with `bst show`.
    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_success()
    assert "git:unlisted-submodule" not in result.stderr

    # We will notice this directly in fetch, as it will try to fetch
    # the submodules it discovers as a result of fetching the primary repo.
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])

    # Assert a warning or an error depending on what we're checking
    if fail == "error":
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, "git:unlisted-submodule")
    else:
        result.assert_success()
        assert "git:unlisted-submodule" in result.stderr

    # Verify that `bst show` will still not error out after fetching.
    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_success()
    assert "git:unlisted-submodule" not in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("fail", ["warn", "error"])
def test_track_unlisted_submodule(cli, tmpdir, datafiles, fail):
    project = str(datafiles)

    # Make the warning an error if we're testing errors
    if fail == "error":
        generate_project(project, config={"fatal-warnings": ["git:unlisted-submodule"]})

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created, but use
    # the original ref, let the submodules appear after tracking
    repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Create the source, and delete the explicit configuration
    # of the submodules.
    gitsource = repo.source_config(ref=ref)
    del gitsource["submodules"]

    # Write out our test target
    element = {"kind": "import", "sources": [gitsource]}
    generate_element(project, "target.bst", element)

    # Fetch the repo, we will not see the warning because we
    # are still pointing to a ref which predates the submodules
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    assert "git:unlisted-submodule" not in result.stderr

    # We won't get a warning/error when tracking either, the source
    # has not become cached so the opportunity to check
    # for the warning has not yet arisen.
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()
    assert "git:unlisted-submodule" not in result.stderr

    # Fetching the repo at the new ref will finally reveal the warning
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    if fail == "error":
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, "git:unlisted-submodule")
    else:
        result.assert_success()
        assert "git:unlisted-submodule" in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("fail", ["warn", "error"])
def test_invalid_submodule(cli, tmpdir, datafiles, fail):
    project = str(datafiles)

    # Make the warning an error if we're testing errors
    if fail == "error":
        generate_project(project, config={"fatal-warnings": ["git:invalid-submodule"]})

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    ref = repo.create(os.path.join(project, "repofiles"))

    # Create the source without any submodules, and add
    # an invalid submodule configuration to it.
    #
    # We expect this to cause an invalid submodule warning
    # after the source has been fetched and we know what
    # the real submodules actually are.
    #
    gitsource = repo.source_config(ref=ref)
    gitsource["submodules"] = {"subdir": {"url": "https://pony.org/repo.git"}}

    # Write out our test target
    element = {"kind": "import", "sources": [gitsource]}
    generate_element(project, "target.bst", element)

    # The warning or error is reported during fetch. There should be no
    # error with `bst show`.
    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_success()
    assert "git:invalid-submodule" not in result.stderr

    # We will notice this directly in fetch, as it will try to fetch
    # the submodules it discovers as a result of fetching the primary repo.
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])

    # Assert a warning or an error depending on what we're checking
    if fail == "error":
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, "git:invalid-submodule")
    else:
        result.assert_success()
        assert "git:invalid-submodule" in result.stderr

    # Verify that `bst show` will still not error out after fetching.
    result = cli.run(project=project, args=["show", "target.bst"])
    result.assert_success()
    assert "git:invalid-submodule" not in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.skipif(HAVE_OLD_GIT, reason="old git rm does not update .gitmodules")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("fail", ["warn", "error"])
def test_track_invalid_submodule(cli, tmpdir, datafiles, fail):
    project = str(datafiles)

    # Make the warning an error if we're testing errors
    if fail == "error":
        generate_project(project, config={"fatal-warnings": ["git:invalid-submodule"]})

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo("git", str(tmpdir), "subrepo")
    subrepo.create(os.path.join(project, "subrepofiles"))

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule("subdir", "file://" + subrepo.repo)

    # Add a commit beyond the ref which *removes* the submodule we've added
    repo.remove_path("subdir")

    # Create the source, this will keep the submodules so initially
    # the configuration is valid for the ref we're using
    gitsource = repo.source_config(ref=ref)

    # Write out our test target
    element = {"kind": "import", "sources": [gitsource]}
    generate_element(project, "target.bst", element)

    # Fetch the repo, we will not see the warning because we
    # are still pointing to a ref which predates the submodules
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()
    assert "git:invalid-submodule" not in result.stderr

    # After tracking we're pointing to a ref, which would trigger an invalid
    # submodule warning. However, cache validation is only performed as part
    # of fetch.
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()

    # Fetch to trigger cache validation
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    if fail == "error":
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.PLUGIN, "git:invalid-submodule")
    else:
        result.assert_success()
        assert "git:invalid-submodule" in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("ref_format", ["sha1", "git-describe"])
@pytest.mark.parametrize("tag,extra_commit", [(False, False), (True, False), (True, True)])
def test_track_fetch(cli, tmpdir, datafiles, ref_format, tag, extra_commit):
    project = str(datafiles)

    # Create the repo from 'repofiles' subdir
    repo = create_repo("git", str(tmpdir))
    repo.create(os.path.join(project, "repofiles"))
    if tag:
        repo.add_tag("tag")
    if extra_commit:
        repo.add_commit()

    # Write out our test target
    element = {"kind": "import", "sources": [repo.source_config()]}
    element["sources"][0]["ref-format"] = ref_format
    generate_element(project, "target.bst", element)
    element_path = os.path.join(project, "target.bst")

    # Track it
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()

    element = load_yaml(element_path)
    new_ref = element.get_sequence("sources").mapping_at(0).get_str("ref")

    if ref_format == "git-describe" and tag:
        # Check and strip prefix
        prefix = "tag-{}-g".format(0 if not extra_commit else 1)
        assert new_ref.startswith(prefix)
        new_ref = new_ref[len(prefix) :]

    # 40 chars for SHA-1
    assert len(new_ref) == 40

    # Fetch it
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.skipif(HAVE_OLD_GIT, reason="old git describe lacks --first-parent")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
@pytest.mark.parametrize("tag_type", [("annotated"), ("lightweight")])
def test_git_describe(cli, tmpdir, datafiles, ref_storage, tag_type):
    project = str(datafiles)

    project_config = load_yaml(os.path.join(project, "project.conf"))
    project_config["ref-storage"] = ref_storage
    generate_project(project, config=project_config)

    repofiles = os.path.join(str(tmpdir), "repofiles")
    os.makedirs(repofiles, exist_ok=True)
    file0 = os.path.join(repofiles, "file0")
    with open(file0, "w") as f:
        f.write("test\n")

    repo = create_repo("git", str(tmpdir))

    def tag(name):
        if tag_type == "annotated":
            repo.add_annotated_tag(name, name)
        else:
            repo.add_tag(name)

    repo.create(repofiles)
    tag("uselesstag")

    file1 = os.path.join(str(tmpdir), "file1")
    with open(file1, "w") as f:
        f.write("test\n")
    repo.add_file(file1)
    tag("tag1")

    file2 = os.path.join(str(tmpdir), "file2")
    with open(file2, "w") as f:
        f.write("test\n")
    repo.branch("branch2")
    repo.add_file(file2)
    tag("tag2")

    repo.checkout("master")
    file3 = os.path.join(str(tmpdir), "file3")
    with open(file3, "w") as f:
        f.write("test\n")
    repo.add_file(file3)

    repo.merge("branch2")

    config = repo.source_config()
    config["track"] = repo.latest_commit()
    config["track-tags"] = True

    # Write out our test target
    element = {
        "kind": "import",
        "sources": [config],
    }
    generate_element(project, "target.bst", element)
    element_path = os.path.join(project, "target.bst")

    if ref_storage == "inline":
        result = cli.run(project=project, args=["source", "track", "target.bst"])
        result.assert_success()
    else:
        result = cli.run(project=project, args=["source", "track", "target.bst", "--deps", "all"])
        result.assert_success()

    if ref_storage == "inline":
        element = load_yaml(element_path)
        tags = element.get_sequence("sources").mapping_at(0).get_sequence("tags")
        assert len(tags) == 2
        for tag in tags:
            assert "tag" in tag
            assert "commit" in tag
            assert "annotated" in tag
            assert tag.get_bool("annotated") == (tag_type == "annotated")

        assert {(tag.get_str("tag"), tag.get_str("commit")) for tag in tags} == {
            ("tag1", repo.rev_parse("tag1^{commit}")),
            ("tag2", repo.rev_parse("tag2^{commit}")),
        }

    checkout = os.path.join(str(tmpdir), "checkout")

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkout])
    result.assert_success()

    if tag_type == "annotated":
        options = []
    else:
        options = ["--tags"]
    describe = subprocess.check_output(["git", "describe", *options], cwd=checkout, universal_newlines=True)
    assert describe.startswith("tag2-2-")

    describe_fp = subprocess.check_output(
        ["git", "describe", "--first-parent", *options], cwd=checkout, universal_newlines=True
    )
    assert describe_fp.startswith("tag1-2-")

    tags = subprocess.check_output(["git", "tag"], cwd=checkout, universal_newlines=True)
    tags = set(tags.splitlines())
    assert tags == set(["tag1", "tag2"])

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(["git", "log", repo.rev_parse("uselesstag")], cwd=checkout, check=True)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
@pytest.mark.parametrize("tag_type", [("annotated"), ("lightweight")])
def test_git_describe_head_is_tagged(cli, tmpdir, datafiles, ref_storage, tag_type):
    project = str(datafiles)

    project_config = load_yaml(os.path.join(project, "project.conf"))
    project_config["ref-storage"] = ref_storage
    generate_project(project, config=project_config)

    repofiles = os.path.join(str(tmpdir), "repofiles")
    os.makedirs(repofiles, exist_ok=True)
    file0 = os.path.join(repofiles, "file0")
    with open(file0, "w") as f:
        f.write("test\n")

    repo = create_repo("git", str(tmpdir))

    def tag(name):
        if tag_type == "annotated":
            repo.add_annotated_tag(name, name)
        else:
            repo.add_tag(name)

    repo.create(repofiles)
    tag("uselesstag")

    file1 = os.path.join(str(tmpdir), "file1")
    with open(file1, "w") as f:
        f.write("test\n")
    repo.add_file(file1)

    file2 = os.path.join(str(tmpdir), "file2")
    with open(file2, "w") as f:
        f.write("test\n")
    repo.branch("branch2")
    repo.add_file(file2)

    repo.checkout("master")
    file3 = os.path.join(str(tmpdir), "file3")
    with open(file3, "w") as f:
        f.write("test\n")
    repo.add_file(file3)

    tagged_ref = repo.merge("branch2")
    tag("tag")

    config = repo.source_config()
    config["track"] = repo.latest_commit()
    config["track-tags"] = True

    # Write out our test target
    element = {
        "kind": "import",
        "sources": [config],
    }
    generate_element(project, "target.bst", element)
    element_path = os.path.join(project, "target.bst")

    if ref_storage == "inline":
        result = cli.run(project=project, args=["source", "track", "target.bst"])
        result.assert_success()
    else:
        result = cli.run(project=project, args=["source", "track", "target.bst", "--deps", "all"])
        result.assert_success()

    if ref_storage == "inline":
        element = load_yaml(element_path)
        source = element.get_sequence("sources").mapping_at(0)
        tags = source.get_sequence("tags")
        assert len(tags) == 1

        tag = source.get_sequence("tags").mapping_at(0)
        assert "tag" in tag
        assert "commit" in tag
        assert "annotated" in tag
        assert tag.get_bool("annotated") == (tag_type == "annotated")

        tag_name = tag.get_str("tag")
        commit = tag.get_str("commit")
        assert (tag_name, commit) == ("tag", repo.rev_parse("tag^{commit}"))

    checkout = os.path.join(str(tmpdir), "checkout")

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkout])
    result.assert_success()

    if tag_type == "annotated":
        options = []
    else:
        options = ["--tags"]
    describe = subprocess.check_output(["git", "describe", *options], cwd=checkout, universal_newlines=True)
    assert describe.startswith("tag")

    tags = subprocess.check_output(["git", "tag"], cwd=checkout, universal_newlines=True)
    tags = set(tags.splitlines())
    assert tags == set(["tag"])

    rev_list = subprocess.check_output(["git", "rev-list", "--all"], cwd=checkout, universal_newlines=True)

    assert set(rev_list.splitlines()) == set([tagged_ref])

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(["git", "log", repo.rev_parse("uselesstag")], cwd=checkout, check=True)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_git_describe_relevant_history(cli, tmpdir, datafiles):
    project = str(datafiles)

    project_config = load_yaml(os.path.join(project, "project.conf"))
    project_config["ref-storage"] = "project.refs"
    generate_project(project, config=project_config)

    repofiles = os.path.join(str(tmpdir), "repofiles")
    os.makedirs(repofiles, exist_ok=True)
    file0 = os.path.join(repofiles, "file0")
    with open(file0, "w") as f:
        f.write("test\n")

    repo = create_repo("git", str(tmpdir))
    repo.create(repofiles)

    file1 = os.path.join(str(tmpdir), "file1")
    with open(file1, "w") as f:
        f.write("test\n")
    repo.add_file(file1)
    repo.branch("branch")
    repo.checkout("master")

    file2 = os.path.join(str(tmpdir), "file2")
    with open(file2, "w") as f:
        f.write("test\n")
    repo.add_file(file2)

    file3 = os.path.join(str(tmpdir), "file3")
    with open(file3, "w") as f:
        f.write("test\n")
    branch_boundary = repo.add_file(file3)

    repo.checkout("branch")
    file4 = os.path.join(str(tmpdir), "file4")
    with open(file4, "w") as f:
        f.write("test\n")
    tagged_ref = repo.add_file(file4)
    repo.add_annotated_tag("tag1", "tag1")

    head = repo.merge("master")

    config = repo.source_config()
    config["track"] = head
    config["track-tags"] = True

    # Write out our test target
    element = {
        "kind": "import",
        "sources": [config],
    }
    generate_element(project, "target.bst", element)

    result = cli.run(project=project, args=["source", "track", "target.bst", "--deps", "all"])
    result.assert_success()

    checkout = os.path.join(str(tmpdir), "checkout")

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", checkout])
    result.assert_success()

    describe = subprocess.check_output(["git", "describe"], cwd=checkout, universal_newlines=True)
    assert describe.startswith("tag1-2-")

    rev_list = subprocess.check_output(["git", "rev-list", "--all"], cwd=checkout, universal_newlines=True)

    assert set(rev_list.splitlines()) == set([head, tagged_ref, branch_boundary])


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_default_do_not_track_tags(cli, tmpdir, datafiles):
    project = str(datafiles)

    project_config = load_yaml(os.path.join(project, "project.conf"))
    project_config["ref-storage"] = "inline"
    generate_project(project, config=project_config)

    repofiles = os.path.join(str(tmpdir), "repofiles")
    os.makedirs(repofiles, exist_ok=True)
    file0 = os.path.join(repofiles, "file0")
    with open(file0, "w") as f:
        f.write("test\n")

    repo = create_repo("git", str(tmpdir))

    repo.create(repofiles)
    repo.add_tag("tag")

    config = repo.source_config()
    config["track"] = repo.latest_commit()

    # Write out our test target
    element = {
        "kind": "import",
        "sources": [config],
    }
    generate_element(project, "target.bst", element)
    element_path = os.path.join(project, "target.bst")

    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()

    element = load_yaml(element_path)
    source = element.get_sequence("sources").mapping_at(0)
    assert "tags" not in source


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, "template"))
def test_overwrite_rogue_tag_multiple_remotes(cli, tmpdir, datafiles):
    """When using multiple remotes in cache (i.e. when using aliases), we
    need to make sure we override tags. This is not allowed to fetch
    tags that were present from different origins
    """

    project = str(datafiles)

    repofiles = os.path.join(str(tmpdir), "repofiles")
    os.makedirs(repofiles, exist_ok=True)
    file0 = os.path.join(repofiles, "file0")
    with open(file0, "w") as f:
        f.write("test\n")

    repo = create_repo("git", str(tmpdir))

    top_commit = repo.create(repofiles)

    repodir, reponame = os.path.split(repo.repo)
    project_config = load_yaml(os.path.join(project, "project.conf"))
    project_config["aliases"] = Node.from_dict({"repo": "http://example.com/"})
    project_config["mirrors"] = [{"name": "middle-earth", "aliases": {"repo": ["file://{}/".format(repodir)]}}]
    generate_project(project, config=project_config)

    repo.add_annotated_tag("tag", "tag")

    file1 = os.path.join(repofiles, "file1")
    with open(file1, "w") as f:
        f.write("test\n")

    ref = repo.add_file(file1)

    config = repo.source_config(ref=ref)
    del config["track"]
    config["url"] = "repo:{}".format(reponame)

    # Write out our test target
    element = {
        "kind": "import",
        "sources": [config],
    }
    generate_element(project, "target.bst", element)

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()

    repo.checkout(top_commit)

    file2 = os.path.join(repofiles, "file2")
    with open(file2, "w") as f:
        f.write("test\n")

    new_ref = repo.add_file(file2)

    repo.delete_tag("tag")
    repo.add_annotated_tag("tag", "tag")
    repo.checkout("master")

    otherpath = os.path.join(str(tmpdir), "other_path")
    shutil.copytree(repo.repo, os.path.join(otherpath, "repo"))
    create_repo("git", otherpath)

    repodir, reponame = os.path.split(repo.repo)

    generate_project(project, config=project_config)

    config = repo.source_config(ref=new_ref)
    del config["track"]
    config["url"] = "repo:{}".format(reponame)

    element = {
        "kind": "import",
        "sources": [config],
    }
    generate_element(project, "target.bst", element)

    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
