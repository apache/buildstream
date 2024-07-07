#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil

import pytest

from buildstream import CoreWarnings, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream._testing import create_repo
from buildstream._testing import cli  # pylint: disable=unused-import

from tests.testutils.repo.git import Git
from tests.testutils.repo.tar import Tar
from tests.testutils.site import pip_sample_packages  # pylint: disable=unused-import
from tests.testutils.site import SAMPLE_PACKAGES_SKIP_REASON


# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def generate_element(output_file):
    element = {
        "kind": "import",
        "sources": [
            {
                "kind": "fetch_source",
                "output-text": output_file,
                "urls": ["foo:repo1", "bar:repo2"],
                "fetch-succeeds": {
                    "FOO/repo1": True,
                    "BAR/repo2": False,
                    "OOF/repo1": False,
                    "RAB/repo2": True,
                    "OFO/repo1": False,
                    "RBA/repo2": False,
                    "ooF/repo1": False,
                    "raB/repo2": False,
                },
            }
        ],
    }
    return element


DEFAULT_MIRROR_LIST = [
    {
        "name": "middle-earth",
        "aliases": {
            "foo": ["OOF/"],
            "bar": ["RAB/"],
        },
    },
    {
        "name": "arrakis",
        "aliases": {
            "foo": ["OFO/"],
            "bar": ["RBA/"],
        },
    },
    {
        "name": "oz",
        "aliases": {
            "foo": ["ooF/"],
            "bar": ["raB/"],
        },
    },
]


SUCCESS_MIRROR_LIST = [
    {
        "name": "middle-earth",
        "aliases": {
            "foo": ["OOF/"],
            "bar": ["RAB/"],
        },
    },
    {
        "name": "arrakis",
        "aliases": {
            "foo": ["FOO/"],
            "bar": ["RBA/"],
        },
    },
    {
        "name": "oz",
        "aliases": {
            "foo": ["ooF/"],
            "bar": ["raB/"],
        },
    },
]


FAIL_MIRROR_LIST = [
    {
        "name": "middle-earth",
        "aliases": {
            "foo": ["pony/"],
            "bar": ["horzy/"],
        },
    },
    {
        "name": "arrakis",
        "aliases": {
            "foo": ["donkey/"],
            "bar": ["rabbit/"],
        },
    },
    {
        "name": "oz",
        "aliases": {
            "foo": ["bear/"],
            "bar": ["buffalo/"],
        },
    },
]


class MirrorConfig:
    NO_MIRRORS = 0
    SUCCESS_MIRRORS = 1
    FAIL_MIRRORS = 2
    DEFAULT_MIRRORS = 3


def generate_project(mirror_config=MirrorConfig.DEFAULT_MIRRORS, base_alias_succeed=False):
    aliases = {
        "foo": "FOO/",
        "bar": "BAR/",
    }
    if base_alias_succeed:
        aliases["bar"] = "RAB/"

    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": aliases,
        "plugins": [{"origin": "local", "path": "sources", "sources": ["fetch_source"]}],
    }
    if mirror_config == MirrorConfig.SUCCESS_MIRRORS:
        project["mirrors"] = SUCCESS_MIRROR_LIST
    elif mirror_config == MirrorConfig.FAIL_MIRRORS:
        project["mirrors"] = FAIL_MIRROR_LIST
    elif mirror_config == MirrorConfig.DEFAULT_MIRRORS:
        project["mirrors"] = DEFAULT_MIRROR_LIST

    return project


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("ref_storage", [("inline"), ("project.refs")])
@pytest.mark.parametrize("mirror", [("no-mirror"), ("mirror"), ("unrelated-mirror")])
def test_mirror_fetch_ref_storage(cli, tmpdir, datafiles, ref_storage, mirror):
    bin_files_path = os.path.join(str(datafiles), "files", "bin-files", "usr")
    dev_files_path = os.path.join(str(datafiles), "files", "dev-files", "usr")
    upstream_repodir = os.path.join(str(tmpdir), "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    project_dir = os.path.join(str(tmpdir), "project")
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo("tar", upstream_repodir)
    upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    upstream_ref = upstream_repo.create(dev_files_path)

    element = {
        "kind": "import",
        "sources": [upstream_repo.source_config(ref=upstream_ref if ref_storage == "inline" else None)],
    }
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    upstream_map, repo_name = os.path.split(full_repo)
    alias = "foo"
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.roundtrip_dump(element, element_path)

    if ref_storage == "project.refs":
        # Manually set project.refs to avoid caching the repo prematurely
        project_refs = {"projects": {"test": {element_name: [{"ref": upstream_ref}]}}}
        project_refs_path = os.path.join(project_dir, "project.refs")
        _yaml.roundtrip_dump(project_refs, project_refs_path)

    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {alias: upstream_map + "/"},
        "ref-storage": ref_storage,
    }
    if mirror != "no-mirror":
        mirror_data = [{"name": "middle-earth", "aliases": {alias: [mirror_map + "/"]}}]
        if mirror == "unrelated-mirror":
            mirror_data.insert(0, {"name": "narnia", "aliases": {"frob": ["http://www.example.com/repo"]}})
        project["mirrors"] = mirror_data

    project_file = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(project, project_file)

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
@pytest.mark.parametrize(
    "project_config,user_config,expect_success",
    [
        # User defined mirror configuration
        (MirrorConfig.NO_MIRRORS, MirrorConfig.SUCCESS_MIRRORS, True),
        # Project defined mirror configuration
        (MirrorConfig.SUCCESS_MIRRORS, MirrorConfig.NO_MIRRORS, True),
        # Both configurations active with success
        (MirrorConfig.FAIL_MIRRORS, MirrorConfig.SUCCESS_MIRRORS, True),
        # Both configurations active with failure, this ensures that
        # the user configuration does not regress to extending project defined
        # mirrors but properly overrides project defined mirrors.
        (MirrorConfig.SUCCESS_MIRRORS, MirrorConfig.FAIL_MIRRORS, False),
    ],
    ids=["user-config", "project-config", "override-success", "override-fail"],
)
def test_mirror_fetch_multi(cli, tmpdir, project_config, user_config, expect_success):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    project_file = os.path.join(project_dir, "project.conf")
    project = generate_project(project_config)
    _yaml.roundtrip_dump(project, project_file)

    if user_config == MirrorConfig.SUCCESS_MIRRORS:
        cli.configure({"projects": {"test": {"mirrors": SUCCESS_MIRROR_LIST}}})
    elif user_config == MirrorConfig.FAIL_MIRRORS:
        cli.configure({"projects": {"test": {"mirrors": FAIL_MIRROR_LIST}}})

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])

    if expect_success:
        result.assert_success()
        with open(output_file, encoding="utf-8") as f:
            contents = f.read()
            assert "Fetch foo:repo1 succeeded from FOO/repo1" in contents
            assert "Fetch bar:repo2 succeeded from RAB/repo2" in contents
    else:
        result.assert_main_error(ErrorDomain.STREAM, None)
        result.assert_task_error(ErrorDomain.SOURCE, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
@pytest.mark.parametrize(
    "project_config,user_config,alias_success,expect_success,source,expect_missing_aliases",
    [
        #
        # Test "alias" fetch source policy (aliases only)
        #
        # Test that we fail to fetch from the primary alias even if the user config defines a mirror
        (MirrorConfig.NO_MIRRORS, MirrorConfig.SUCCESS_MIRRORS, False, False, "aliases", False),
        # Test that we fail to fetch from the primary alias even if the project config defines a mirror
        (MirrorConfig.SUCCESS_MIRRORS, MirrorConfig.NO_MIRRORS, False, False, "aliases", False),
        # Test that we succeed to fetch from the primary alias even if the user config defines a failing mirror
        (MirrorConfig.FAIL_MIRRORS, MirrorConfig.FAIL_MIRRORS, True, True, "aliases", False),
        #
        # Test "mirrors" fetch source policy (mirrors only, no base aliases)
        #
        # Test that we fail to fetch from primary alias even if it is the only one configured to succeed
        (MirrorConfig.FAIL_MIRRORS, MirrorConfig.FAIL_MIRRORS, True, False, "mirrors", False),
        # Test that we succeed to fetch from mirrors when primary alias is set to succeed
        # (doesn't prove that primary alias is not consulted, but tests that we indeed consult
        # mirrors when configued in mirror mode)
        (MirrorConfig.SUCCESS_MIRRORS, MirrorConfig.NO_MIRRORS, True, True, "mirrors", False),
        (MirrorConfig.FAIL_MIRRORS, MirrorConfig.SUCCESS_MIRRORS, True, True, "mirrors", False),
        #
        # Test preflight errors when there are missing mirror alias targets
        #
        (MirrorConfig.NO_MIRRORS, MirrorConfig.NO_MIRRORS, True, False, "mirrors", True),
        #
        # Test "user" fetch source policy (only mirrors defined in user configuration)
        #
        # Test that we fail to fetch even if the alias is good and the project defined mirrors are good
        (MirrorConfig.SUCCESS_MIRRORS, MirrorConfig.FAIL_MIRRORS, True, False, "user", False),
        # Test that we succeed to fetch when alias is bad and project mirrors are bad
        # (this doesn't prove that project aliases and mirrors are not consulted, but here for completeness)
        (MirrorConfig.FAIL_MIRRORS, MirrorConfig.SUCCESS_MIRRORS, False, True, "user", False),
    ],
    ids=[
        "aliases-fail-user-config",
        "aliases-fail-project-config",
        "aliases-success-bad-mirrors",
        "mirrors-fail-bad-mirrors",
        "mirrors-success-project-config",
        "mirrors-success-user-config",
        "mirrors-fail-inactive",
        "user-fail",
        "user-succees",
    ],
)
def test_mirror_fetch_source(
    cli, tmpdir, project_config, user_config, alias_success, expect_success, source, expect_missing_aliases
):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    project_file = os.path.join(project_dir, "project.conf")
    project = generate_project(project_config, alias_success)
    _yaml.roundtrip_dump(project, project_file)

    # Configure the fetch source
    cli.configure({"fetch": {"source": source}})

    if user_config == MirrorConfig.SUCCESS_MIRRORS:
        cli.configure({"projects": {"test": {"mirrors": SUCCESS_MIRROR_LIST}}})
    elif user_config == MirrorConfig.FAIL_MIRRORS:
        cli.configure({"projects": {"test": {"mirrors": FAIL_MIRROR_LIST}}})

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])

    if expect_success:
        result.assert_success()
        with open(output_file, encoding="utf-8") as f:
            contents = f.read()
            assert "Fetch foo:repo1 succeeded from FOO/repo1" in contents
            assert "Fetch bar:repo2 succeeded from RAB/repo2" in contents
    else:
        #
        # Special case check this failure mode
        #
        if expect_missing_aliases:
            result.assert_main_error(ErrorDomain.SOURCE, "missing-source-alias-target")
        else:
            result.assert_main_error(ErrorDomain.STREAM, None)
            result.assert_task_error(ErrorDomain.SOURCE, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
def test_mirror_fetch_default_cmdline(cli, tmpdir):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    project_file = os.path.join(project_dir, "project.conf")
    project = generate_project()
    _yaml.roundtrip_dump(project, project_file)

    result = cli.run(project=project_dir, args=["--default-mirror", "arrakis", "source", "fetch", element_name])
    result.assert_success()
    with open(output_file, encoding="utf-8") as f:
        contents = f.read()
        print(contents)
        # Success if fetching from arrakis' mirror happened before middle-earth's
        arrakis_str = "OFO/repo1"
        arrakis_pos = contents.find(arrakis_str)
        assert arrakis_pos != -1, "'{}' wasn't found".format(arrakis_str)
        me_str = "OOF/repo1"
        me_pos = contents.find(me_str)
        assert me_pos != -1, "'{}' wasn't found".format(me_str)
        assert arrakis_pos < me_pos, "'{}' wasn't found before '{}'".format(arrakis_str, me_str)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
def test_mirror_fetch_default_userconfig(cli, tmpdir):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    project_file = os.path.join(project_dir, "project.conf")
    project = generate_project()
    _yaml.roundtrip_dump(project, project_file)

    userconfig = {"projects": {"test": {"default-mirror": "oz"}}}
    cli.configure(userconfig)

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()
    with open(output_file, encoding="utf-8") as f:
        contents = f.read()
        print(contents)
        # Success if fetching from Oz' mirror happened before middle-earth's
        oz_str = "ooF/repo1"
        oz_pos = contents.find(oz_str)
        assert oz_pos != -1, "'{}' wasn't found".format(oz_str)
        me_str = "OOF/repo1"
        me_pos = contents.find(me_str)
        assert me_pos != -1, "'{}' wasn't found".format(me_str)
        assert oz_pos < me_pos, "'{}' wasn't found before '{}'".format(oz_str, me_str)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
def test_mirror_fetch_default_cmdline_overrides_config(cli, tmpdir):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    project_file = os.path.join(project_dir, "project.conf")
    project = generate_project()
    _yaml.roundtrip_dump(project, project_file)

    userconfig = {"projects": {"test": {"default-mirror": "oz"}}}
    cli.configure(userconfig)

    result = cli.run(project=project_dir, args=["--default-mirror", "arrakis", "source", "fetch", element_name])
    result.assert_success()
    with open(output_file, encoding="utf-8") as f:
        contents = f.read()
        print(contents)
        # Success if fetching from arrakis' mirror happened before middle-earth's
        arrakis_str = "OFO/repo1"
        arrakis_pos = contents.find(arrakis_str)
        assert arrakis_pos != -1, "'{}' wasn't found".format(arrakis_str)
        me_str = "OOF/repo1"
        me_pos = contents.find(me_str)
        assert me_pos != -1, "'{}' wasn't found".format(me_str)
        assert arrakis_pos < me_pos, "'{}' wasn't found before '{}'".format(arrakis_str, me_str)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_mirror_git_submodule_fetch(cli, tmpdir, datafiles):
    # Test that it behaves as expected with submodules, both defined in config
    # and discovered when fetching.
    foo_file = os.path.join(str(datafiles), "files", "foo")
    bar_file = os.path.join(str(datafiles), "files", "bar")
    bin_files_path = os.path.join(str(datafiles), "files", "bin-files", "usr")
    dev_files_path = os.path.join(str(datafiles), "files", "dev-files", "usr")
    mirror_dir = os.path.join(str(datafiles), "mirror")

    defined_subrepo = Git(str(tmpdir), "defined_subrepo")
    defined_subrepo.create(bin_files_path)
    defined_subrepo.copy(mirror_dir)
    defined_subrepo.add_file(foo_file)

    found_subrepo = Git(str(tmpdir), "found_subrepo")
    found_subrepo.create(dev_files_path)

    main_repo = Git(str(tmpdir))
    main_mirror_ref = main_repo.create(bin_files_path)
    main_repo.add_submodule("defined", "file://" + defined_subrepo.repo)
    main_repo.add_submodule("found", "file://" + found_subrepo.repo)
    main_mirror = main_repo.copy(mirror_dir)
    main_repo.add_file(bar_file)

    project_dir = os.path.join(str(tmpdir), "project")
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir)
    element = {"kind": "import", "sources": [main_repo.source_config(ref=main_mirror_ref)]}
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)

    # Alias the main repo
    full_repo = element["sources"][0]["url"]
    _, repo_name = os.path.split(full_repo)
    alias = "foo"
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo

    # Hide the found subrepo
    del element["sources"][0]["submodules"]["found"]

    # Alias the defined subrepo
    subrepo = element["sources"][0]["submodules"]["defined"]["url"]
    _, repo_name = os.path.split(subrepo)
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["submodules"]["defined"]["url"] = aliased_repo

    _yaml.roundtrip_dump(element, element_path)

    full_mirror = main_mirror.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {alias: "http://www.example.com/"},
        "plugins": [
            {
                "origin": "pip",
                "package-name": "sample-plugins",
                "sources": ["git"],
            }
        ],
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            },
        ],
    }
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(project, project_file)

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_mirror_fallback_git_only_submodules(cli, tmpdir, datafiles):
    # Main repo has no mirror or alias.
    # One submodule is overridden to use a mirror.
    # There is another submodules not overriden.
    # Upstream for overriden submodule is down.
    #
    # We expect:
    #  - overriden submodule is fetched from mirror.
    #  - other submodule is fetched.

    bin_files_path = os.path.join(str(datafiles), "files", "bin-files", "usr")
    dev_files_path = os.path.join(str(datafiles), "files", "dev-files", "usr")

    upstream_bin_repodir = os.path.join(str(tmpdir), "bin-upstream")
    mirror_bin_repodir = os.path.join(str(tmpdir), "bin-mirror")
    upstream_bin_repo = Git(upstream_bin_repodir)
    upstream_bin_repo.create(bin_files_path)
    mirror_bin_repo = upstream_bin_repo.copy(mirror_bin_repodir)

    dev_repodir = os.path.join(str(tmpdir), "dev-upstream")
    dev_repo = Git(dev_repodir)
    dev_repo.create(dev_files_path)

    main_files = os.path.join(str(tmpdir), "main-files")
    os.makedirs(main_files)
    with open(os.path.join(main_files, "README"), "w", encoding="utf-8") as f:
        f.write("TEST\n")
    main_repodir = os.path.join(str(tmpdir), "main-upstream")
    main_repo = Git(main_repodir)
    main_repo.create(main_files)

    upstream_url = "file://{}".format(upstream_bin_repo.repo)
    main_repo.add_submodule("bin", url=upstream_url)
    main_repo.add_submodule("dev", url="file://{}".format(dev_repo.repo))
    # Unlist 'dev'.
    del main_repo.submodules["dev"]

    main_ref = main_repo.latest_commit()

    upstream_map, repo_name = os.path.split(upstream_url)
    alias = "foo"
    aliased_repo = "{}:{}".format(alias, repo_name)
    main_repo.submodules["bin"]["url"] = aliased_repo

    full_mirror = mirror_bin_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)

    project_dir = os.path.join(str(tmpdir), "project")
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, "elements")

    element = {"kind": "import", "sources": [main_repo.source_config_extra(ref=main_ref, checkout_submodules=True)]}
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    os.makedirs(element_dir)
    _yaml.roundtrip_dump(element, element_path)

    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {alias: upstream_map + "/"},
        "plugins": [
            {
                "origin": "pip",
                "package-name": "sample-plugins",
                "sources": ["git"],
            }
        ],
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            }
        ],
    }
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(project, project_file)

    # Now make the upstream unavailable.
    os.rename(upstream_bin_repo.repo, "{}.bak".format(upstream_bin_repo.repo))
    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()

    result = cli.run(project=project_dir, args=["build", element_name])
    result.assert_success()

    checkout = os.path.join(str(tmpdir), "checkout")
    result = cli.run(project=project_dir, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, "bin", "bin", "hello"))
    assert os.path.exists(os.path.join(checkout, "dev", "include", "pony.h"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif("not pip_sample_packages()", reason=SAMPLE_PACKAGES_SKIP_REASON)
def test_mirror_fallback_git_with_submodules(cli, tmpdir, datafiles):
    # Main repo has mirror. But does not list submodules.
    #
    # We expect:
    #  - we will fetch submodules anyway

    bin_files_path = os.path.join(str(datafiles), "files", "bin-files", "usr")
    dev_files_path = os.path.join(str(datafiles), "files", "dev-files", "usr")

    bin_repodir = os.path.join(str(tmpdir), "bin-repo")
    bin_repo = Git(bin_repodir)
    bin_repo.create(bin_files_path)

    dev_repodir = os.path.join(str(tmpdir), "dev-repo")
    dev_repo = Git(dev_repodir)
    dev_repo.create(dev_files_path)

    main_files = os.path.join(str(tmpdir), "main-files")
    os.makedirs(main_files)
    with open(os.path.join(main_files, "README"), "w", encoding="utf-8") as f:
        f.write("TEST\n")
    upstream_main_repodir = os.path.join(str(tmpdir), "main-upstream")
    upstream_main_repo = Git(upstream_main_repodir)
    upstream_main_repo.create(main_files)

    upstream_main_repo.add_submodule("bin", url="file://{}".format(bin_repo.repo))
    upstream_main_repo.add_submodule("dev", url="file://{}".format(dev_repo.repo))
    # Unlist submodules.
    del upstream_main_repo.submodules["bin"]
    del upstream_main_repo.submodules["dev"]

    upstream_main_ref = upstream_main_repo.latest_commit()

    mirror_main_repodir = os.path.join(str(tmpdir), "main-mirror")
    mirror_main_repo = upstream_main_repo.copy(mirror_main_repodir)

    upstream_url = mirror_main_repo.source_config()["url"]

    upstream_map, repo_name = os.path.split(upstream_url)
    alias = "foo"
    aliased_repo = "{}:{}".format(alias, repo_name)

    full_mirror = mirror_main_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)

    project_dir = os.path.join(str(tmpdir), "project")
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, "elements")

    element = {
        "kind": "import",
        "sources": [upstream_main_repo.source_config_extra(ref=upstream_main_ref, checkout_submodules=True)],
    }
    element["sources"][0]["url"] = aliased_repo
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    os.makedirs(element_dir)
    _yaml.roundtrip_dump(element, element_path)

    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {alias: upstream_map + "/"},
        "plugins": [
            {
                "origin": "pip",
                "package-name": "sample-plugins",
                "sources": ["git"],
            }
        ],
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            }
        ],
    }
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(project, project_file)

    # Now make the upstream unavailable.
    os.rename(upstream_main_repo.repo, "{}.bak".format(upstream_main_repo.repo))
    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()

    result = cli.run(project=project_dir, args=["build", element_name])
    result.assert_success()

    checkout = os.path.join(str(tmpdir), "checkout")
    result = cli.run(project=project_dir, args=["artifact", "checkout", element_name, "--directory", checkout])
    result.assert_success()

    assert os.path.exists(os.path.join(checkout, "bin", "bin", "hello"))
    assert os.path.exists(os.path.join(checkout, "dev", "include", "pony.h"))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
def test_mirror_expand_project_and_toplevel_root(cli, tmpdir):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    project_file = os.path.join(project_dir, "project.conf")
    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {
            "foo": "FOO/",
            "bar": "BAR/",
        },
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    "foo": ["OOF/"],
                    "bar": ["RAB/"],
                },
            },
            {
                "name": "arrakis",
                "aliases": {
                    "foo": ["%{project-root}/OFO/"],
                    "bar": ["%{project-root}/RBA/"],
                },
            },
            {
                "name": "oz",
                "aliases": {
                    "foo": ["ooF/"],
                    "bar": ["raB/"],
                },
            },
        ],
        "plugins": [{"origin": "local", "path": "sources", "sources": ["fetch_source"]}],
    }

    _yaml.roundtrip_dump(project, project_file)

    result = cli.run(project=project_dir, args=["--default-mirror", "arrakis", "source", "fetch", element_name])
    result.assert_success()
    with open(output_file, encoding="utf-8") as f:
        contents = f.read()
        print(contents)
        foo_str = os.path.join(project_dir, "OFO/repo1")
        bar_str = os.path.join(project_dir, "RBA/repo2")

        # Success if the expanded %{project-root} is found
        assert foo_str in contents
        assert bar_str in contents


# Test a simple SourceMirror implementation which reads
# plugin configuration and behaves in the same way as default
# mirrors but using data in the plugin configuration instead.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
@pytest.mark.parametrize("origin", [("local"), ("junction"), ("pip")])
def test_source_mirror_plugin(cli, tmpdir, origin):
    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    element = generate_element(output_file)
    _yaml.roundtrip_dump(element, element_path)

    def source_mirror_plugin_origin():
        if origin == "local":
            return {"origin": "local", "path": "sourcemirrors", "source-mirrors": ["mirror"]}
        elif origin == "pip":
            return {
                "origin": "pip",
                "package-name": "sample-plugins>=1.2",
                "source-mirrors": ["mirror"],
            }
        elif origin == "junction":
            # For junction loading, just copy in the sample-plugins into a subdir and
            # create a local junction
            sample_plugins_dir = os.path.join(TOP_DIR, "..", "plugins", "sample-plugins")
            sample_plugins_copy_dir = os.path.join(project_dir, "sample-plugins-copy")
            junction_file = os.path.join(element_dir, "sample-plugins.bst")

            shutil.copytree(sample_plugins_dir, sample_plugins_copy_dir)

            _yaml.roundtrip_dump(
                {"kind": "junction", "sources": [{"kind": "local", "path": "sample-plugins-copy"}]}, junction_file
            )

            return {
                "origin": "junction",
                "junction": "sample-plugins.bst",
                "source-mirrors": ["mirror"],
            }
        else:
            assert False

    project_file = os.path.join(project_dir, "project.conf")
    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {
            "foo": "FOO/",
            "bar": "BAR/",
        },
        "mirrors": [
            {
                "name": "middle-earth",
                "kind": "mirror",
                "config": {
                    "aliases": {
                        "foo": ["OOF/"],
                        "bar": ["RAB/"],
                    },
                },
            },
            {
                "name": "arrakis",
                "kind": "mirror",
                "config": {
                    "aliases": {
                        "foo": ["%{project-root}/OFO/"],
                        "bar": ["%{project-root}/RBA/"],
                    },
                },
            },
            {
                "name": "oz",
                "kind": "mirror",
                "config": {
                    "aliases": {
                        "foo": ["ooF/"],
                        "bar": ["raB/"],
                    },
                },
            },
        ],
        "plugins": [
            {"origin": "local", "path": "sources", "sources": ["fetch_source"]},
            source_mirror_plugin_origin(),
        ],
    }

    _yaml.roundtrip_dump(project, project_file)

    result = cli.run(project=project_dir, args=["--default-mirror", "arrakis", "source", "fetch", element_name])
    result.assert_success()
    with open(output_file, encoding="utf-8") as f:
        contents = f.read()
        print(contents)
        foo_str = os.path.join(project_dir, "OFO/repo1")
        bar_str = os.path.join(project_dir, "RBA/repo2")

        # Success if the expanded %{project-root} is found
        assert foo_str in contents
        assert bar_str in contents


# Test subproject alias mapping. As there are quite a few corner cases and interactions with other
# features that need to be tested, this test relies heavily on parametrization. Here is what each
# parameter means:
# * subproject_mirrors: whether the subproject defines a (failing) mirror
# * unaliased_sources: whether the subproject has unaliased sources
# * disallow_subproject_uris: define disallow-subproject-uris in the parent project
# * fetch_source: whether to fetch from aliases or mirrors
# * alias_override: which aliases to override ("global" means use "map-aliases")
# * alias_mapping: how to map aliases to the overrides
# * source_mirror: whether to use a custom source mirror plugin


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.usefixtures("datafiles")
@pytest.mark.parametrize("subproject_mirrors", [True, False])
@pytest.mark.parametrize("unaliased_sources", [True, False])
@pytest.mark.parametrize("disallow_subproject_uris", [True, False])
@pytest.mark.parametrize("fetch_source", ["aliases", "mirrors"])
@pytest.mark.parametrize("alias_override", [["foo"], ["foo", "bar"], "global"])
@pytest.mark.parametrize("alias_mapping", ["identity", "project-prefix", "invalid"])
@pytest.mark.parametrize("source_mirror", [True, False])
def test_mirror_subproject_aliases(
    cli,
    tmpdir,
    subproject_mirrors,
    unaliased_sources,
    disallow_subproject_uris,
    fetch_source,
    alias_override,
    alias_mapping,
    source_mirror,
):
    if alias_override == "global":
        if alias_mapping == "invalid":
            # we can't have an invalid mapping using a predefined option
            pytest.skip()
        elif alias_mapping == "project-prefix":
            # project-prefix alias mapping not yet implemented
            pytest.xfail()

    output_file = os.path.join(str(tmpdir), "output.txt")
    project_dir = tmpdir

    element_dir = project_dir / "elements"
    os.makedirs(element_dir, exist_ok=True)

    subproject_dir = project_dir / "subproject"
    subproject_element_dir = subproject_dir / "elements"
    os.makedirs(subproject_element_dir, exist_ok=True)

    subproject_bar_alias_succeed = (
        fetch_source == "aliases" and not disallow_subproject_uris and alias_override == ["foo"]
    )

    subproject = {
        "name": "test-subproject",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {
            "foo": "OOF/",
            "bar": "RAB/" if subproject_bar_alias_succeed else "BAR/",
        },
        "plugins": [
            {"origin": "local", "path": "sources", "sources": ["fetch_source"]},
        ],
    }

    if subproject_mirrors:
        subproject["mirrors"] = FAIL_MIRROR_LIST

    _yaml.roundtrip_dump(subproject, str(subproject_dir / "project.conf"))

    element_name = "test.bst"
    element = generate_element(output_file)

    if unaliased_sources:
        element["sources"][0]["urls"] = ["foo:repo1", "RAB/repo2"]
    _yaml.roundtrip_dump(element, str(subproject_element_dir / element_name))

    # copy the source plugin to the subproject
    shutil.copytree(project_dir / "sources", subproject_dir / "sources")

    if alias_mapping == "identity":

        def map_alias(x):
            return x

    elif alias_mapping == "project-prefix":

        def map_alias(x):
            return subproject["name"] + "/" + x

    else:

        def map_alias(x):
            return "invalid-" + x

    if alias_mapping != "invalid":
        map_alias_valid = map_alias
    else:

        def map_alias_valid(x):
            return x

    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {
            map_alias_valid("foo"): "FOO/",
            map_alias_valid("bar"): "RAB/" if fetch_source == "aliases" else "BAR/",
        },
        "plugins": [{"origin": "local", "path": "sources", "sources": ["fetch_source"]}],
        # Copy of SUCCESS_MIRROR_LIST from above
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    map_alias_valid("foo"): ["OOF/"],
                    map_alias_valid("bar"): ["RAB/"],
                },
            },
            {
                "name": "arrakis",
                "aliases": {
                    map_alias_valid("foo"): ["FOO/"],
                    map_alias_valid("bar"): ["RBA/"],
                },
            },
            {
                "name": "oz",
                "aliases": {
                    map_alias_valid("foo"): ["ooF/"],
                    map_alias_valid("bar"): ["raB/"],
                },
            },
        ],
    }
    if source_mirror:
        project["plugins"].append({"origin": "local", "path": "sourcemirrors", "source-mirrors": ["mirror"]})

        mirrors = []
        for mirror in project["mirrors"]:
            mirrors.append({"name": mirror["name"], "kind": "mirror", "config": {"aliases": mirror["aliases"]}})
        project["mirrors"] = mirrors

    if disallow_subproject_uris:
        project["junctions"] = {"disallow-subproject-uris": "true"}

    _yaml.roundtrip_dump(project, str(project_dir / "project.conf"))

    junction_name = "subproject.bst"
    junction = {
        "kind": "junction",
        "sources": [
            {
                "kind": "local",
                "path": "subproject",
            }
        ],
    }

    if alias_override == "global":
        junction["config"] = {"map-aliases": alias_mapping}
    else:
        junction["config"] = {"aliases": {alias: map_alias(alias) for alias in alias_override}}

    _yaml.roundtrip_dump(junction, str(element_dir / junction_name))

    userconfig = {"fetch": {"source": fetch_source}}
    cli.configure(userconfig)

    result = cli.run(project=project_dir, args=["source", "fetch", "{}:{}".format(junction_name, element_name)])
    if alias_mapping == "invalid":
        # Mapped alias does not exist in the parent project
        result.assert_main_error(ErrorDomain.SOURCE, "invalid-source-alias")
    elif disallow_subproject_uris and unaliased_sources:
        # Subproject defines unaliased source and the parent project disallows subproject URIs
        result.assert_main_error(ErrorDomain.PLUGIN, CoreWarnings.UNALIASED_URL)
    elif disallow_subproject_uris and alias_override == ["foo"]:
        # No alias mapping defined for `bar` and the parent project disallows subproject URIs
        result.assert_main_error(ErrorDomain.SOURCE, "missing-alias-mapping")
    elif fetch_source == "mirrors" and not unaliased_sources and alias_override == ["foo"]:
        # Mirror required and no alias mapping defined for `bar`
        if not subproject_mirrors:
            # and the subproject has no mirror configured
            result.assert_main_error(ErrorDomain.SOURCE, "missing-source-alias-target")
        else:
            # and the subproject has a failing mirror configured
            result.assert_task_error(ErrorDomain.SOURCE, None)

            with open(output_file, encoding="utf-8") as f:
                contents = f.read()

                assert "Fetch foo:repo1 succeeded from FOO/repo1" in contents
                assert "Fetch bar:repo2 failed from rabbit/repo2" in contents
                assert "Fetch bar:repo2 failed from buffalo/repo2" in contents
    else:
        result.assert_success()

        with open(output_file, encoding="utf-8") as f:
            contents = f.read()

            assert "Fetch foo:repo1 succeeded from FOO/repo1" in contents

            if unaliased_sources:
                assert "Fetch RAB/repo2 succeeded from RAB/repo2" in contents
            else:
                assert "Fetch bar:repo2 succeeded from RAB/repo2" in contents


# Test the behavior of loading a SourceMirror plugin across a junction,
# when the cross junction SourceMirror object has a mirror.
#
# Check what happens when the mirror does not need to be exercized (success)
#
# Check what happens when the mirror needs to be exercised in order to obtain
# the mirror plugin itself (failure) and check the failure mode.
#
#
@pytest.mark.parametrize("fetch_source", [("all"), ("mirrors")], ids=["normal", "circular"])
def test_source_mirror_circular_junction(cli, tmpdir, fetch_source):
    project_dir = str(tmpdir)
    element_dir = os.path.join(project_dir, "elements")
    os.makedirs(element_dir, exist_ok=True)

    cli.configure({"fetch": {"source": fetch_source}})

    # Generate a 2 tar repos with the sample plugins
    #
    sample_plugins_dir = os.path.join(TOP_DIR, "..", "plugins", "sample-plugins")
    base_sample_plugins_repodir = os.path.join(str(tmpdir), "base_sample_plugins")
    base_sample_plugins_repo = Tar(base_sample_plugins_repodir)
    base_sample_plugins_ref = base_sample_plugins_repo.create(sample_plugins_dir)
    mirror_sample_plugins_repodir = os.path.join(str(tmpdir), "mirror_sample_plugins")
    mirror_sample_plugins_repo = Tar(mirror_sample_plugins_repodir)

    # Don't expect determinism from python tar, just copy over the Tar repo file
    # and we need to use the same ref for both.
    shutil.copyfile(
        os.path.join(base_sample_plugins_repo.repo, "file.tar.gz"),
        os.path.join(mirror_sample_plugins_repo.repo, "file.tar.gz"),
    )

    # Generate junction for sample plugins
    #
    sample_plugins_junction = {
        "kind": "junction",
        "sources": [
            {
                "kind": "tar",
                "url": "samplemirror:file.tar.gz",
                "ref": base_sample_plugins_ref,
            }
        ],
    }
    element_path = os.path.join(element_dir, "sample-plugins.bst")
    _yaml.roundtrip_dump(sample_plugins_junction, element_path)

    # Generate project.conf
    #
    project_file = os.path.join(project_dir, "project.conf")
    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {
            "samplemirror": "file://" + base_sample_plugins_repo.repo + "/",
        },
        "mirrors": [
            {
                "name": "alternative",
                "kind": "mirror",
                "config": {
                    "aliases": {
                        "samplemirror": ["file://" + mirror_sample_plugins_repo.repo + "/"],
                    },
                },
            },
        ],
        "plugins": [
            {"origin": "junction", "junction": "sample-plugins.bst", "source-mirrors": ["mirror"]},
        ],
    }
    _yaml.roundtrip_dump(project, project_file)

    # Make a silly element
    element = {"kind": "import", "sources": [{"kind": "local", "path": "project.conf"}]}
    element_path = os.path.join(element_dir, "test.bst")
    _yaml.roundtrip_dump(element, element_path)

    result = cli.run(project=project_dir, args=["show", "test.bst"])

    if fetch_source == "all":
        result.assert_success()
    elif fetch_source == "mirrors":
        #
        # This error looks like this:
        #
        #   Error loading project: tar source at sample-plugins.bst [line 3 column 2]: No fetch URI found for alias 'samplemirror'
        #
        #       Check fetch controls in your user configuration
        #
        # This is not 100% ideal, as we could theoretically have Source.mark_download_url() detect
        # the case that we are currently instantiating the specific SourceMirror plugin required
        # to resolve the URL needed to obtain the same said SourceMirror plugin, and report
        # something about this being a circular dependency error.
        #
        # However, this would be fairly complex to reason about in the code, especially considering
        # the source alias redirects, and the possibility that a subproject's source mirror is being
        # redirected to a parent project's aliases and corresponding mirrors.
        #
        result.assert_main_error(ErrorDomain.SOURCE, "missing-source-alias-target")
