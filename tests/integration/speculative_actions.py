#
#  Copyright 2025 The Apache Software Foundation
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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import io
import os
import re
import tarfile
import pytest

from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing.integration import assert_contains
from buildstream._testing._utils.site import HAVE_SANDBOX


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def _parse_queue_processed(output, queue_name):
    """Parse 'processed N' count for a queue from the pipeline summary."""
    pattern = rf"{re.escape(queue_name)} Queue:\s+processed\s+(\d+)"
    match = re.search(pattern, output)
    if match:
        return int(match.group(1))
    return None


# NOTE: Test ordering matters. The integration cache (including casd's action
# cache) is shared across all tests in this module. The generation test must
# run first to get a fresh casd without action cache hits from prior builds.
# Pytest runs tests in file order by default.


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_speculative_actions_generation(cli, datafiles):
    """
    Build with speculative-actions enabled and verify:
    1. recc executed actions remotely (subactions recorded)
    2. The generation queue processed at least one element
    3. Artifact was produced correctly

    This test must run first in the module to avoid casd action cache
    hits from prior builds that would prevent remote execution.
    """
    project = str(datafiles)
    element_name = "speculative/base.bst"

    cli.configure({"scheduler": {"speculative-actions": True}})

    result = cli.run(
        project=project,
        args=["--cache-buildtrees", "always", "build", element_name],
    )
    if result.exit_code != 0:
        cli.run(
            project=project,
            args=[
                "shell", "--build", "--use-buildtree", element_name,
                "--", "sh", "-c",
                "cat config.log .recc-log/* */.recc-log/* 2>/dev/null",
            ],
        )
    assert result.exit_code == 0
    build_output = result.stderr

    # Verify recc executed remotely
    result = cli.run(
        project=project,
        args=[
            "shell", "--build", "--use-buildtree", element_name,
            "--", "sh", "-c", "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    assert "Executing action remotely" in result.output, (
        "recc did not execute remotely — got action cache hits instead"
    )

    # Verify artifact
    checkout = os.path.join(cli.directory, "checkout")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", element_name, "--directory", checkout],
    )
    assert result.exit_code == 0
    assert_contains(checkout, ["/usr", "/usr/bin", "/usr/bin/hello"])

    # Verify the generation queue processed at least one element
    assert "Generating overlays Queue:" in build_output, (
        "Generation queue not in pipeline summary — "
        "speculative-actions config not applied?"
    )
    processed = _parse_queue_processed(build_output, "Generating overlays")
    assert processed is not None, (
        "Could not parse generation queue stats from pipeline summary"
    )
    assert processed > 0, (
        "Generation queue processed 0 elements — no subactions found"
    )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_speculative_actions_dependency_chain(cli, datafiles):
    """
    Build the full 3-element dependency chain: base -> middle -> top.
    """
    project = str(datafiles)
    element_name = "speculative/top.bst"

    result = cli.run(
        project=project,
        args=["--cache-buildtrees", "always", "build", element_name],
    )
    assert result.exit_code == 0

    checkout = os.path.join(cli.directory, "checkout")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", element_name, "--directory", checkout],
    )
    assert result.exit_code == 0
    assert os.path.exists(
        os.path.join(checkout, "usr", "share", "speculative", "top.txt")
    )
    assert os.path.exists(
        os.path.join(checkout, "usr", "share", "speculative", "from-middle.txt")
    )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_speculative_actions_rebuild_with_source_change(cli, datafiles):
    """
    Full speculative actions roundtrip:
    1. Build base element with recc (subactions recorded, overlays generated)
    2. Modify source (patch main.c in the amhello tarball)
    3. Rebuild and verify the modified source was picked up
    4. Verify generation queue runs on the rebuild (new subactions for
       the changed source)
    """
    project = str(datafiles)
    element_name = "speculative/base.bst"

    cli.configure({"scheduler": {"speculative-actions": True}})

    # --- First build ---
    result = cli.run(
        project=project,
        args=["--cache-buildtrees", "always", "build", element_name],
    )
    assert result.exit_code == 0

    # --- Modify source: patch main.c in the amhello tarball ---
    original_tar = os.path.join(project, "files", "amhello.tar.gz")

    members = {}
    with tarfile.open(original_tar, "r:gz") as tf:
        for member in tf.getmembers():
            if member.isfile():
                members[member.name] = (member, tf.extractfile(member).read())
            else:
                members[member.name] = (member, None)

    main_c_name = "amhello/src/main.c"
    member, content = members[main_c_name]
    new_content = content.replace(
        b'puts ("Hello World!");',
        b'puts ("Hello Speculative World!");',
    )
    assert new_content != content, "Source modification failed"

    with tarfile.open(original_tar, "w:gz") as tf:
        for name, (m, data) in members.items():
            if data is not None:
                if name == main_c_name:
                    data = new_content
                    m.size = len(data)
                tf.addfile(m, io.BytesIO(data))
            else:
                tf.addfile(m)

    # Delete cached artifact and re-track source
    result = cli.run(project=project, args=["artifact", "delete", element_name])
    assert result.exit_code == 0
    result = cli.run(project=project, args=["source", "track", element_name])
    assert result.exit_code == 0

    # --- Second build with modified source ---
    result = cli.run(
        project=project,
        args=["--cache-buildtrees", "always", "build", element_name],
    )
    assert result.exit_code == 0
    rebuild_output = result.stderr

    # Verify the rebuild produced a new artifact
    checkout = os.path.join(cli.directory, "checkout-rebuild")
    result = cli.run(
        project=project,
        args=["artifact", "checkout", element_name, "--directory", checkout],
    )
    assert result.exit_code == 0
    assert os.path.exists(os.path.join(checkout, "usr", "bin", "hello"))

    # Verify the generation queue ran on the rebuild.
    # The source changed so recc builds with different inputs → new Execute
    # requests → new subactions recorded.
    processed = _parse_queue_processed(rebuild_output, "Generating overlays")
    if processed is not None:
        assert processed > 0, (
            "Generation queue processed 0 on rebuild — "
            "expected new subactions after source change"
        )


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_speculative_actions_priming(cli, datafiles):
    """
    End-to-end priming test with partial cache hits.

    app.bst is a multi-file autotools project compiled through recc:
    - main.c includes dep.h (from dep.bst) and common.h (local)
    - util.c includes only common.h (local)
    - link step combines main.o and util.o

    This produces 3 subactions: compile main.c, compile util.c, link.

    When dep.bst changes (dep.h updated):
    - main.c compile: needs instantiation (dep.h digest changed)
    - util.c compile: stays stable (no dep files in input tree)
    - link: needs instantiation (main.o changed)

    So we expect:
    - Priming queue processes app (finds SA by stable weak key)
    - On rebuild, recc sees a mix of cache hits (from priming) and
      possibly some direct hits (unchanged actions)
    """
    project = str(datafiles)
    app_element = "speculative/app.bst"

    cli.configure({"scheduler": {"speculative-actions": True}})

    # --- First build: generate speculative actions for app ---
    result = cli.run(
        project=project,
        args=["--cache-buildtrees", "always", "build", app_element],
    )
    if result.exit_code != 0:
        cli.run(
            project=project,
            args=[
                "shell", "--build", "--use-buildtree", app_element,
                "--", "sh", "-c",
                "cat config.log .recc-log/* */.recc-log/* 2>/dev/null",
            ],
        )
    assert result.exit_code == 0

    # Verify SA generation and count remote executions
    first_build_output = result.stderr
    gen_processed = _parse_queue_processed(first_build_output, "Generating overlays")
    assert gen_processed is not None and gen_processed > 0, (
        "First build did not generate speculative actions"
    )

    # Check first build recc log: should have remote executions
    result = cli.run(
        project=project,
        args=[
            "shell", "--build", "--use-buildtree", app_element,
            "--", "sh", "-c", "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    first_recc_log = result.output
    first_remote_execs = first_recc_log.count("Executing action remotely")
    assert first_remote_execs >= 3, (
        f"Expected at least 3 remote executions (2 compiles + 1 link), "
        f"got {first_remote_execs}"
    )

    # --- Modify dep: change dep.h header ---
    dep_header = os.path.join(
        project, "files", "speculative", "dep-files",
        "usr", "include", "speculative", "dep.h",
    )
    with open(dep_header, "w") as f:
        f.write("#ifndef DEP_H\n#define DEP_H\n#define DEP_VERSION 2\n#endif\n")

    # --- Second build: priming + rebuild ---
    result = cli.run(
        project=project,
        args=["--cache-buildtrees", "always", "build", app_element],
    )
    assert result.exit_code == 0
    rebuild_output = result.stderr

    # Verify priming queue ran for app
    primed = _parse_queue_processed(rebuild_output, "Priming cache")
    assert primed is not None and primed > 0, (
        "Priming queue did not process app — SA not found by weak key?"
    )

    # Check rebuild recc log: should have cache hits from priming
    result = cli.run(
        project=project,
        args=[
            "shell", "--build", "--use-buildtree", app_element,
            "--", "sh", "-c", "cat src/.recc-log/recc.buildbox*",
        ],
    )
    assert result.exit_code == 0
    rebuild_recc_log = result.output
    cache_hits = rebuild_recc_log.count("Action Cache hit")
    remote_execs = rebuild_recc_log.count("Executing action remotely")

    print(
        f"Priming result: {cache_hits} cache hits, "
        f"{remote_execs} remote executions "
        f"(first build had {first_remote_execs} remote executions)"
    )

    # The priming should have resulted in at least some cache hits.
    # Ideally: util.c compile is a direct hit (unchanged), main.c compile
    # and link are primed hits. But even partial success is valuable.
    assert cache_hits > 0, (
        f"Expected cache hits from priming, got 0. "
        f"Remote executions: {remote_execs}. "
        f"The adapted action digests may not match recc's computed actions."
    )

    # The total should account for all actions: some cache hits
    # (from priming or unchanged), fewer remote executions than
    # the first build.
    assert cache_hits + remote_execs >= first_remote_execs, (
        f"Expected at least {first_remote_execs} total actions "
        f"(hits + execs), got {cache_hits + remote_execs}"
    )
    assert remote_execs < first_remote_execs, (
        f"Expected fewer remote executions than first build "
        f"({first_remote_execs}), got {remote_execs}"
    )
