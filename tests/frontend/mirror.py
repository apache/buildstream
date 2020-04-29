# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml
from buildstream.testing import create_repo
from buildstream.testing import cli  # pylint: disable=unused-import


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


def generate_project():
    project = {
        "name": "test",
        "min-version": "2.0",
        "element-path": "elements",
        "aliases": {"foo": "FOO/", "bar": "BAR/",},
        "mirrors": [
            {"name": "middle-earth", "aliases": {"foo": ["OOF/"], "bar": ["RAB/"],},},
            {"name": "arrakis", "aliases": {"foo": ["OFO/"], "bar": ["RBA/"],},},
            {"name": "oz", "aliases": {"foo": ["ooF/"], "bar": ["raB/"],}},
        ],
        "plugins": [{"origin": "local", "path": "sources", "sources": ["fetch_source"]}],
    }
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
def test_mirror_fetch_multi(cli, tmpdir):
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

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()
    with open(output_file) as f:
        contents = f.read()
        assert "Fetch foo:repo1 succeeded from FOO/repo1" in contents
        assert "Fetch bar:repo2 succeeded from RAB/repo2" in contents


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
    with open(output_file) as f:
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
    with open(output_file) as f:
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
    with open(output_file) as f:
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
def test_mirror_git_submodule_fetch(cli, tmpdir, datafiles):
    # Test that it behaves as expected with submodules, both defined in config
    # and discovered when fetching.
    foo_file = os.path.join(str(datafiles), "files", "foo")
    bar_file = os.path.join(str(datafiles), "files", "bar")
    bin_files_path = os.path.join(str(datafiles), "files", "bin-files", "usr")
    dev_files_path = os.path.join(str(datafiles), "files", "dev-files", "usr")
    mirror_dir = os.path.join(str(datafiles), "mirror")

    defined_subrepo = create_repo("git", str(tmpdir), "defined_subrepo")
    defined_subrepo.create(bin_files_path)
    defined_subrepo.copy(mirror_dir)
    defined_subrepo.add_file(foo_file)

    found_subrepo = create_repo("git", str(tmpdir), "found_subrepo")
    found_subrepo.create(dev_files_path)

    main_repo = create_repo("git", str(tmpdir))
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
        "mirrors": [{"name": "middle-earth", "aliases": {alias: [mirror_map + "/"],},},],
    }
    project_file = os.path.join(project_dir, "project.conf")
    _yaml.roundtrip_dump(project, project_file)

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
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
    upstream_bin_repo = create_repo("git", upstream_bin_repodir)
    upstream_bin_repo.create(bin_files_path)
    mirror_bin_repo = upstream_bin_repo.copy(mirror_bin_repodir)

    dev_repodir = os.path.join(str(tmpdir), "dev-upstream")
    dev_repo = create_repo("git", dev_repodir)
    dev_repo.create(dev_files_path)

    main_files = os.path.join(str(tmpdir), "main-files")
    os.makedirs(main_files)
    with open(os.path.join(main_files, "README"), "w") as f:
        f.write("TEST\n")
    main_repodir = os.path.join(str(tmpdir), "main-upstream")
    main_repo = create_repo("git", main_repodir)
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
        "mirrors": [{"name": "middle-earth", "aliases": {alias: [mirror_map + "/"],}}],
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
def test_mirror_fallback_git_with_submodules(cli, tmpdir, datafiles):
    # Main repo has mirror. But does not list submodules.
    #
    # We expect:
    #  - we will fetch submodules anyway

    bin_files_path = os.path.join(str(datafiles), "files", "bin-files", "usr")
    dev_files_path = os.path.join(str(datafiles), "files", "dev-files", "usr")

    bin_repodir = os.path.join(str(tmpdir), "bin-repo")
    bin_repo = create_repo("git", bin_repodir)
    bin_repo.create(bin_files_path)

    dev_repodir = os.path.join(str(tmpdir), "dev-repo")
    dev_repo = create_repo("git", dev_repodir)
    dev_repo.create(dev_files_path)

    main_files = os.path.join(str(tmpdir), "main-files")
    os.makedirs(main_files)
    with open(os.path.join(main_files, "README"), "w") as f:
        f.write("TEST\n")
    upstream_main_repodir = os.path.join(str(tmpdir), "main-upstream")
    upstream_main_repo = create_repo("git", upstream_main_repodir)
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
        "mirrors": [{"name": "middle-earth", "aliases": {alias: [mirror_map + "/"],}}],
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
