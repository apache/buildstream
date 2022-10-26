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
import pytest

from buildstream import _yaml
from buildstream.exceptions import ErrorDomain
from .._utils import generate_junction
from .. import create_repo
from .. import cli  # pylint: disable=unused-import
from .utils import kind  # pylint: disable=unused-import

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, "project")


def _set_project_mirrors_and_aliases(project_path, mirrors, aliases):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf["mirrors"] = mirrors
    project_conf["aliases"].update(aliases)

    _yaml.roundtrip_dump(project_conf, project_conf_path)


def _set_project_includes_and_aliases(project_path, includes, aliases):
    project_conf_path = os.path.join(project_path, "project.conf")
    project_conf = _yaml.roundtrip_load(project_conf_path)

    project_conf["aliases"].update(aliases)
    project_conf["(@)"] = includes

    _yaml.roundtrip_dump(project_conf, project_conf_path)


@pytest.mark.datafiles(DATA_DIR)
def test_mirror_fetch(cli, tmpdir, datafiles, kind):
    project_dir = str(datafiles)
    bin_files_path = os.path.join(project_dir, "files", "bin-files", "usr")
    dev_files_path = os.path.join(project_dir, "files", "dev-files", "usr")
    upstream_repodir = os.path.join(str(tmpdir), "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    upstream_ref = upstream_repo.create(dev_files_path)

    element = {"kind": "import", "sources": [upstream_repo.source_config(ref=upstream_ref)]}
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    upstream_map, repo_name = os.path.split(full_repo)
    alias = "foo-" + kind
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    _yaml.roundtrip_dump(element, element_path)

    _set_project_mirrors_and_aliases(
        project_dir,
        [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            },
        ],
        {alias: upstream_map + "/"},
    )

    # No obvious ways of checking that the mirror has been fetched
    # But at least we can be sure it succeeds
    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_mirror_fetch_upstream_absent(cli, tmpdir, datafiles, kind):
    project_dir = str(datafiles)
    dev_files_path = os.path.join(project_dir, "files", "dev-files", "usr")
    upstream_repodir = os.path.join(project_dir, "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    ref = upstream_repo.create(dev_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)

    element = {"kind": "import", "sources": [upstream_repo.source_config(ref=ref)]}

    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    _, repo_name = os.path.split(full_repo)
    alias = "foo-" + kind
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    _yaml.roundtrip_dump(element, element_path)

    _set_project_mirrors_and_aliases(
        project_dir,
        [
            {
                "name": "middle-earth",
                "aliases": {alias: [mirror_map + "/"]},
            },
        ],
        {alias: "http://www.example.com"},
    )

    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_mirror_from_includes(cli, tmpdir, datafiles, kind):
    project_dir = str(datafiles)
    bin_files_path = os.path.join(project_dir, "files", "bin-files", "usr")
    upstream_repodir = os.path.join(str(tmpdir), "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_ref = upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)

    element = {"kind": "import", "sources": [upstream_repo.source_config(ref=upstream_ref)]}
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    upstream_map, repo_name = os.path.split(full_repo)
    alias = "foo-" + kind
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    _yaml.roundtrip_dump(element, element_path)

    config_project_dir = str(tmpdir.join("config"))
    os.makedirs(config_project_dir, exist_ok=True)
    config_project = {"name": "config", "min-version": "2.0"}
    _yaml.roundtrip_dump(config_project, os.path.join(config_project_dir, "project.conf"))
    extra_mirrors = {
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            }
        ]
    }
    _yaml.roundtrip_dump(extra_mirrors, os.path.join(config_project_dir, "mirrors.yml"))
    generate_junction(str(tmpdir.join("config_repo")), config_project_dir, os.path.join(element_dir, "config.bst"))

    _set_project_includes_and_aliases(
        project_dir,
        ["config.bst:mirrors.yml"],
        {alias: upstream_map + "/"},
    )

    # Now make the upstream unavailable.
    os.rename(upstream_repo.repo, "{}.bak".format(upstream_repo.repo))
    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_mirror_junction_from_includes(cli, tmpdir, datafiles, kind):
    project_dir = str(datafiles)
    bin_files_path = os.path.join(project_dir, "files", "bin-files", "usr")
    upstream_repodir = os.path.join(str(tmpdir), "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_ref = upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)

    element = {"kind": "junction", "sources": [upstream_repo.source_config(ref=upstream_ref)]}
    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    upstream_map, repo_name = os.path.split(full_repo)
    alias = "foo-" + kind
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    _yaml.roundtrip_dump(element, element_path)

    config_project_dir = str(tmpdir.join("config"))
    os.makedirs(config_project_dir, exist_ok=True)
    config_project = {"name": "config", "min-version": "2.0"}
    _yaml.roundtrip_dump(config_project, os.path.join(config_project_dir, "project.conf"))
    extra_mirrors = {
        "mirrors": [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            }
        ]
    }
    _yaml.roundtrip_dump(extra_mirrors, os.path.join(config_project_dir, "mirrors.yml"))
    generate_junction(str(tmpdir.join("config_repo")), config_project_dir, os.path.join(element_dir, "config.bst"))

    _set_project_includes_and_aliases(project_dir, ["config.bst:mirrors.yml"], {alias: upstream_map + "/"})

    # Now make the upstream unavailable.
    os.rename(upstream_repo.repo, "{}.bak".format(upstream_repo.repo))
    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_main_error(ErrorDomain.STREAM, None)
    # Now make the upstream available again.
    os.rename("{}.bak".format(upstream_repo.repo), upstream_repo.repo)
    result = cli.run(project=project_dir, args=["source", "fetch", element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_mirror_track_upstream_present(cli, tmpdir, datafiles, kind):
    project_dir = str(datafiles)
    bin_files_path = os.path.join(project_dir, "files", "bin-files", "usr")
    dev_files_path = os.path.join(project_dir, "files", "dev-files", "usr")
    upstream_repodir = os.path.join(str(tmpdir), "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    upstream_ref = upstream_repo.create(dev_files_path)

    element = {"kind": "import", "sources": [upstream_repo.source_config(ref=upstream_ref)]}

    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    upstream_map, repo_name = os.path.split(full_repo)
    alias = "foo-" + kind
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    _yaml.roundtrip_dump(element, element_path)

    _set_project_mirrors_and_aliases(
        project_dir,
        [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            },
        ],
        {alias: upstream_map + "/"},
    )

    result = cli.run(project=project_dir, args=["source", "track", element_name])
    result.assert_success()

    # Tracking tries upstream first. Check the ref is from upstream.
    new_element = _yaml.load(element_path, shortname=element_name)
    source = new_element.get_sequence("sources").mapping_at(0)
    if "ref" in source:
        assert source.get_str("ref") == upstream_ref


@pytest.mark.datafiles(DATA_DIR)
def test_mirror_track_upstream_absent(cli, tmpdir, datafiles, kind):
    project_dir = str(datafiles)
    bin_files_path = os.path.join(project_dir, "files", "bin-files", "usr")
    dev_files_path = os.path.join(project_dir, "files", "dev-files", "usr")
    upstream_repodir = os.path.join(str(tmpdir), "upstream")
    mirror_repodir = os.path.join(str(tmpdir), "mirror")
    element_dir = os.path.join(project_dir, "elements")

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_ref = upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    mirror_ref = upstream_ref
    upstream_ref = upstream_repo.create(dev_files_path)

    # Configure to allow tracking mirrors as well as upstream
    cli.configure({"track": {"source": "all"}})

    element = {"kind": "import", "sources": [upstream_repo.source_config(ref=upstream_ref)]}

    element_name = "test.bst"
    element_path = os.path.join(element_dir, element_name)
    full_repo = element["sources"][0]["url"]
    _, repo_name = os.path.split(full_repo)
    alias = "foo-" + kind
    aliased_repo = alias + ":" + repo_name
    element["sources"][0]["url"] = aliased_repo
    full_mirror = mirror_repo.source_config()["url"]
    mirror_map, _ = os.path.split(full_mirror)
    _yaml.roundtrip_dump(element, element_path)

    _set_project_mirrors_and_aliases(
        project_dir,
        [
            {
                "name": "middle-earth",
                "aliases": {
                    alias: [mirror_map + "/"],
                },
            },
        ],
        {alias: "http://www.example.com"},
    )

    result = cli.run(project=project_dir, args=["source", "track", element_name])
    result.assert_success()

    # Check that tracking fell back to the mirror
    new_element = _yaml.load(element_path, shortname=element_name)
    source = new_element.get_sequence("sources").mapping_at(0)
    if "ref" in source:
        assert source.get_str("ref") == mirror_ref
