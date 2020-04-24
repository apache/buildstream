# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import itertools
import os

import pytest

from buildstream._remote import RemoteSpec, RemoteType
from buildstream._artifactcache import ArtifactCache
from buildstream._project import Project
from buildstream.utils import _deduplicate
from buildstream import _yaml
from buildstream.exceptions import ErrorDomain, LoadErrorReason

from buildstream.testing.runcli import cli  # pylint: disable=unused-import

from tests.testutils import dummy_context


DATA_DIR = os.path.dirname(os.path.realpath(__file__))
cache1 = RemoteSpec(url="https://example.com/cache1", push=True)
cache2 = RemoteSpec(url="https://example.com/cache2", push=False)
cache3 = RemoteSpec(url="https://example.com/cache3", push=False)
cache4 = RemoteSpec(url="https://example.com/cache4", push=False)
cache5 = RemoteSpec(url="https://example.com/cache5", push=False)
cache6 = RemoteSpec(url="https://example.com/cache6", push=True, type=RemoteType.ALL)
cache7 = RemoteSpec(url="https://index.example.com/cache1", push=True, type=RemoteType.INDEX)
cache8 = RemoteSpec(url="https://storage.example.com/cache1", push=True, type=RemoteType.STORAGE)


# Generate cache configuration fragments for the user config and project config files.
#
def configure_remote_caches(override_caches, project_caches=None, user_caches=None):
    type_strings = {RemoteType.INDEX: "index", RemoteType.STORAGE: "storage", RemoteType.ALL: "all"}

    if project_caches is None:
        project_caches = []

    if user_caches is None:
        user_caches = []

    user_config = {}
    if len(user_caches) == 1:
        user_config["artifacts"] = {
            "url": user_caches[0].url,
            "push": user_caches[0].push,
            "type": type_strings[user_caches[0].type],
        }
    elif len(user_caches) > 1:
        user_config["artifacts"] = [
            {"url": cache.url, "push": cache.push, "type": type_strings[cache.type]} for cache in user_caches
        ]

    if len(override_caches) == 1:
        user_config["projects"] = {
            "test": {
                "artifacts": {
                    "url": override_caches[0].url,
                    "push": override_caches[0].push,
                    "type": type_strings[override_caches[0].type],
                }
            }
        }
    elif len(override_caches) > 1:
        user_config["projects"] = {
            "test": {
                "artifacts": [
                    {"url": cache.url, "push": cache.push, "type": type_strings[cache.type]}
                    for cache in override_caches
                ]
            }
        }

    project_config = {}
    if project_caches:
        if len(project_caches) == 1:
            project_config.update(
                {
                    "artifacts": {
                        "url": project_caches[0].url,
                        "push": project_caches[0].push,
                        "type": type_strings[project_caches[0].type],
                    }
                }
            )
        elif len(project_caches) > 1:
            project_config.update(
                {
                    "artifacts": [
                        {"url": cache.url, "push": cache.push, "type": type_strings[cache.type]}
                        for cache in project_caches
                    ]
                }
            )

    return user_config, project_config


# Test that parsing the remote artifact cache locations produces the
# expected results.
@pytest.mark.parametrize(
    "override_caches, project_caches, user_caches",
    [
        # The leftmost cache is the highest priority one in all cases here.
        pytest.param([], [], [], id="empty-config"),
        pytest.param([], [], [cache1, cache2], id="user-config"),
        pytest.param([], [cache1, cache2], [cache3], id="project-config"),
        pytest.param([cache1], [cache2], [cache3], id="project-override-in-user-config"),
        pytest.param([cache1, cache2], [cache3, cache4], [cache5, cache6], id="list-order"),
        pytest.param([cache1, cache2, cache1], [cache2], [cache2, cache1], id="duplicates"),
        pytest.param([cache7, cache8], [], [cache1], id="split-caches"),
    ],
)
def test_artifact_cache_precedence(tmpdir, override_caches, project_caches, user_caches):
    # Produce a fake user and project config with the cache configuration.
    user_config, project_config = configure_remote_caches(override_caches, project_caches, user_caches)
    project_config["name"] = "test"
    project_config["min-version"] = "2.0"

    user_config_file = str(tmpdir.join("buildstream.conf"))
    _yaml.roundtrip_dump(user_config, file=user_config_file)

    project_dir = tmpdir.mkdir("project")
    project_config_file = str(project_dir.join("project.conf"))
    _yaml.roundtrip_dump(project_config, file=project_config_file)

    with dummy_context(config=user_config_file) as context:
        project = Project(str(project_dir), context)
        project.ensure_fully_loaded()

        # Use the helper from the artifactcache module to parse our configuration.
        parsed_cache_specs = ArtifactCache._configured_remote_cache_specs(context, project)

        # Verify that it was correctly read.
        expected_cache_specs = list(_deduplicate(itertools.chain(override_caches, project_caches, user_caches)))
        assert parsed_cache_specs == expected_cache_specs


# Assert that if either the client key or client cert is specified
# without specifying its counterpart, we get a comprehensive LoadError
# instead of an unhandled exception.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("config_key, config_value", [("client-cert", "client.crt"), ("client-key", "client.key")])
def test_missing_certs(cli, datafiles, config_key, config_value):
    project = os.path.join(datafiles.dirname, datafiles.basename, "missing-certs")

    project_conf = {
        "name": "test",
        "artifacts": {"url": "https://cache.example.com:12345", "push": "true", config_key: config_value},
    }
    project_conf_file = os.path.join(project, "project.conf")
    _yaml.roundtrip_dump(project_conf, project_conf_file)

    # Use `pull` here to ensure we try to initialize the remotes, triggering the error
    #
    # This does not happen for a simple `bst show`.
    result = cli.run(project=project, args=["artifact", "pull", "element.bst"])
    result.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.INVALID_DATA)


# Assert that BuildStream complains when someone attempts to define
# only one type of storage.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "override_caches, project_caches, user_caches",
    [
        # The leftmost cache is the highest priority one in all cases here.
        pytest.param([], [], [cache7], id="index-user"),
        pytest.param([], [], [cache8], id="storage-user"),
        pytest.param([], [cache7], [], id="index-project"),
        pytest.param([], [cache8], [], id="storage-project"),
        pytest.param([cache7], [], [], id="index-override"),
        pytest.param([cache8], [], [], id="storage-override"),
    ],
)
def test_only_one(cli, datafiles, override_caches, project_caches, user_caches):
    project = os.path.join(datafiles.dirname, datafiles.basename, "only-one")

    # Produce a fake user and project config with the cache configuration.
    user_config, project_config = configure_remote_caches(override_caches, project_caches, user_caches)
    project_config["name"] = "test"
    project_config["min-version"] = "2.0"

    cli.configure(user_config)

    project_config_file = os.path.join(project, "project.conf")
    _yaml.roundtrip_dump(project_config, file=project_config_file)

    # Use `pull` here to ensure we try to initialize the remotes, triggering the error
    #
    # This does not happen for a simple `bst show`.
    result = cli.run(project=project, args=["artifact", "pull", "element.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "artifacts_config",
    (
        {
            "url": "http://localhost.test",
            "server-cert": "~/server.crt",
            "client-cert": "~/client.crt",
            "client-key": "~/client.key",
        },
        [
            {
                "url": "http://localhost.test",
                "server-cert": "~/server.crt",
                "client-cert": "~/client.crt",
                "client-key": "~/client.key",
            },
            {
                "url": "http://localhost2.test",
                "server-cert": "~/server2.crt",
                "client-cert": "~/client2.crt",
                "client-key": "~/client2.key",
            },
        ],
    ),
)
@pytest.mark.parametrize("in_user_config", [True, False])
def test_paths_for_artifact_config_are_expanded(tmpdir, monkeypatch, artifacts_config, in_user_config):
    # Produce a fake user and project config with the cache configuration.
    # user_config, project_config = configure_remote_caches(override_caches, project_caches, user_caches)
    # project_config['name'] = 'test'

    monkeypatch.setenv("HOME", str(tmpdir.join("homedir")))

    project_config = {"name": "test", "min-version": "2.0"}
    user_config = {}
    if in_user_config:
        user_config["artifacts"] = artifacts_config
    else:
        project_config["artifacts"] = artifacts_config

    user_config_file = str(tmpdir.join("buildstream.conf"))
    _yaml.roundtrip_dump(user_config, file=user_config_file)

    project_dir = tmpdir.mkdir("project")
    project_config_file = str(project_dir.join("project.conf"))
    _yaml.roundtrip_dump(project_config, file=project_config_file)

    with dummy_context(config=user_config_file) as context:
        project = Project(str(project_dir), context)
        project.ensure_fully_loaded()

        # Use the helper from the artifactcache module to parse our configuration.
        parsed_cache_specs = ArtifactCache._configured_remote_cache_specs(context, project)

    if isinstance(artifacts_config, dict):
        artifacts_config = [artifacts_config]

    # Build expected artifact config
    artifacts_config = [
        RemoteSpec(
            url=config["url"],
            push=False,
            server_cert=os.path.expanduser(config["server-cert"]),
            client_cert=os.path.expanduser(config["client-cert"]),
            client_key=os.path.expanduser(config["client-key"]),
        )
        for config in artifacts_config
    ]

    assert parsed_cache_specs == artifacts_config
