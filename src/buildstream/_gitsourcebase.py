#
#  Copyright (C) 2016 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Chandan Singh <csingh43@bloomberg.net>

"""Abstract base class for source implementations that work with a Git repository"""

import os
import re
import shutil
from io import StringIO
from tempfile import TemporaryFile

from configparser import RawConfigParser

from .source import Source, SourceError, SourceFetcher
from .types import Consistency, CoreWarnings
from . import utils
from .types import FastEnum
from .utils import move_atomic, DirectoryExistsError

GIT_MODULES = ".gitmodules"

# Warnings
WARN_INCONSISTENT_SUBMODULE = "inconsistent-submodule"
WARN_UNLISTED_SUBMODULE = "unlisted-submodule"
WARN_INVALID_SUBMODULE = "invalid-submodule"


class _RefFormat(FastEnum):
    SHA1 = "sha1"
    GIT_DESCRIBE = "git-describe"


# _has_matching_ref():
#
# Args:
#     refs: Iterable of string (ref id, ref name) pairs
#     tag (str): Tag name
#     commit (str): Commit ID
#
# Returns:
#     (bool): Whether the given tag is found in `refs` and points to ID `commit`
#
def _has_matching_ref(refs, tag, commit):
    names = ("refs/tags/{tag}^{{}}".format(tag=tag), "refs/tags/{tag}".format(tag=tag))
    return any(ref_commit == commit and ref_name in names for ref_commit, ref_name in refs)


# This class represents a single Git repository. The Git source needs to account for
# submodules, but we don't want to cache them all under the umbrella of the
# superproject - so we use this class which caches them independently, according
# to their URL. Instances keep reference to their "parent" GitSourceBase,
# and if applicable, where in the superproject they are found.
#
# Args:
#    source (_GitSourceBase or subclass): The parent source
#    path (str): The relative location of the submodule in the superproject;
#                the empty string for the superproject itself
#    url (str): Where to clone the repo from
#    ref (str): Specified 'ref' from the source configuration
#    primary (bool): Whether this is the primary URL for the source
#    tags (list): Tag configuration; see _GitSourceBase._load_tags
#
class _GitMirror(SourceFetcher):
    def __init__(self, source, path, url, ref, *, primary=False, tags=[]):

        super().__init__()
        self.source = source
        self.path = path
        self.url = url
        self.ref = ref
        self.tags = tags
        self.primary = primary
        self.mirror = os.path.join(source.get_mirror_directory(), utils.url_directory_name(url))

    # _ensure_repo():
    #
    # Ensures that the Git repository exists at the mirror location and is configured
    # to fetch from the given URL
    #
    def _ensure_repo(self):
        if not os.path.exists(self.mirror):
            with self.source.tempdir() as tmpdir:
                self.source.call(
                    [self.source.host_git, "init", "--bare", tmpdir], fail="Failed to initialise repository",
                )

                try:
                    move_atomic(tmpdir, self.mirror)
                except DirectoryExistsError:
                    # Another process was quicker to download this repository.
                    # Let's discard our own
                    self.source.status("{}: Discarding duplicate repository".format(self.source))
                except OSError as e:
                    raise SourceError(
                        "{}: Failed to move created repository from '{}' to '{}': {}".format(
                            self.source, tmpdir, self.mirror, e
                        )
                    ) from e

    def _fetch(self, url):
        self._ensure_repo()

        fetch_all = False

        # Work out whether we can fetch a specific tag: are we given a ref which
        # 1. is in git-describe format
        # 2. refers to an exact tag (is "...-0-g...")
        # 3. is available on the remote and tags the specified commit?
        if not self.ref:
            fetch_all = True
        else:
            m = re.match(r"(?P<tag>.*)-0-g(?P<commit>.*)", self.ref)
            if m is None:
                fetch_all = True
            else:
                tag = m.group("tag")
                commit = m.group("commit")

                _, ls_remote = self.source.check_output(
                    [self.source.host_git, "ls-remote", url],
                    cwd=self.mirror,
                    fail="Failed to list advertised remote refs from git repository {}".format(url),
                )

                refs = [line.split("\t", 1) for line in ls_remote.splitlines()]
                has_ref = _has_matching_ref(refs, tag, commit)

                if not has_ref:
                    self.source.status(
                        "{}: {} is not advertised on {}. Fetching all Git refs".format(self.source, self.ref, url)
                    )
                    fetch_all = True
                else:
                    exit_code = self.source.call(
                        [
                            self.source.host_git,
                            "fetch",
                            "--depth=1",
                            url,
                            "+refs/tags/{tag}:refs/tags/{tag}".format(tag=tag),
                        ],
                        cwd=self.mirror,
                    )
                    if exit_code != 0:
                        self.source.status(
                            "{}: Failed to fetch tag '{}' from {}. Fetching all Git refs".format(self.source, tag, url)
                        )
                        fetch_all = True

        if fetch_all:
            self.source.call(
                [
                    self.source.host_git,
                    "fetch",
                    "--prune",
                    url,
                    "+refs/heads/*:refs/heads/*",
                    "+refs/tags/*:refs/tags/*",
                ],
                fail="Failed to fetch from remote git repository: {}".format(url),
                fail_temporarily=True,
                cwd=self.mirror,
            )

    def fetch(self, alias_override=None):  # pylint: disable=arguments-differ
        resolved_url = self.source.translate_url(self.url, alias_override=alias_override, primary=self.primary)

        with self.source.timed_activity("Fetching from {}".format(resolved_url), silent_nested=True):
            if not self.has_ref():
                self._fetch(resolved_url)
            self.assert_ref()

    def has_ref(self):
        if not self.ref:
            return False

        # If the mirror doesnt exist, we also dont have the ref
        if not os.path.exists(self.mirror):
            return False

        # Check if the ref is really there
        rc = self.source.call([self.source.host_git, "cat-file", "-t", self.ref], cwd=self.mirror)
        return rc == 0

    def assert_ref(self):
        if not self.has_ref():
            raise SourceError(
                "{}: expected ref '{}' was not found in git repository: '{}'".format(self.source, self.ref, self.url)
            )

    # latest_commit():
    #
    # Args:
    #     branch (str)
    #
    # Returns:
    #     (str): The commit rev of the latest commit on the given branch
    #
    def latest_commit(self, branch):
        _, output = self.source.check_output(
            [self.source.host_git, "rev-parse", branch],
            fail="Unable to find commit for specified branch name '{}'".format(branch),
            cwd=self.mirror,
        )
        return output.strip()

    # describe():
    #
    # Args:
    #     rev (str): A Git "commit-ish" rev
    #
    # Returns:
    #     (str): A human-readable form of the rev as produced by git-describe,
    #            or the rev itself if it cannot be described
    #
    def describe(self, rev):
        exit_code, output = self.source.check_output(
            [self.source.host_git, "describe", "--tags", "--abbrev=40", "--long", rev], cwd=self.mirror,
        )

        if exit_code == 0:
            rev = output.strip()

        return rev

    # reachable_tags():
    #
    # Args:
    #     rev (str): A Git "commit-ish" rev
    #
    # Returns:
    #     (list): A list of (tag name (str), commit ref (str), annotated (bool))
    #             triples describing a tag, its tagged commit and whether it's annotated
    #
    def reachable_tags(self, rev):
        tags = set()
        for options in [[], ["--first-parent"], ["--tags"], ["--tags", "--first-parent"]]:
            exit_code, output = self.source.check_output(
                [self.source.host_git, "describe", "--abbrev=0", rev, *options], cwd=self.mirror
            )
            if exit_code == 0:
                tag = output.strip()
                _, commit_ref = self.source.check_output(
                    [self.source.host_git, "rev-parse", tag + "^{commit}"],
                    fail="Unable to resolve tag '{}'".format(tag),
                    cwd=self.mirror,
                )
                exit_code = self.source.call([self.source.host_git, "cat-file", "tag", tag], cwd=self.mirror)
                annotated = exit_code == 0

                tags.add((tag, commit_ref.strip(), annotated))

        return list(tags)

    def stage(self, directory):
        fullpath = os.path.join(directory, self.path)

        # Using --shared here avoids copying the objects into the checkout, in any
        # case we're just checking out a specific commit and then removing the .git/
        # directory.
        self.source.call(
            [self.source.host_git, "clone", "--no-checkout", "--shared", self.mirror, fullpath],
            fail="Failed to create git mirror {} in directory: {}".format(self.mirror, fullpath),
            fail_temporarily=True,
        )

        self.source.call(
            [self.source.host_git, "checkout", "--force", self.ref],
            fail="Failed to checkout git ref {}".format(self.ref),
            cwd=fullpath,
        )

        # Remove .git dir
        shutil.rmtree(os.path.join(fullpath, ".git"))

        self._rebuild_git(fullpath)

    def init_workspace(self, directory):
        fullpath = os.path.join(directory, self.path)
        url = self.source.translate_url(self.url)

        self.source.call(
            [self.source.host_git, "clone", "--no-checkout", self.mirror, fullpath],
            fail="Failed to clone git mirror {} in directory: {}".format(self.mirror, fullpath),
            fail_temporarily=True,
        )

        self.source.call(
            [self.source.host_git, "remote", "set-url", "origin", url],
            fail='Failed to add remote origin "{}"'.format(url),
            cwd=fullpath,
        )

        self.source.call(
            [self.source.host_git, "checkout", "--force", self.ref],
            fail="Failed to checkout git ref {}".format(self.ref),
            cwd=fullpath,
        )

    # get_submodule_mirrors():
    #
    # Returns:
    #     An iterator through new instances of this class, one of each submodule
    #     in the repo
    #
    def get_submodule_mirrors(self):
        for path, url in self.submodule_list():
            ref = self.submodule_ref(path)
            if ref is not None:
                mirror = self.__class__(self.source, os.path.join(self.path, path), url, ref)
                yield mirror

    # List the submodules (path/url tuples) present at the given ref of this repo
    def submodule_list(self):
        modules = "{}:{}".format(self.ref, GIT_MODULES)
        exit_code, output = self.source.check_output([self.source.host_git, "show", modules], cwd=self.mirror)

        # If git show reports error code 128 here, we take it to mean there is
        # no .gitmodules file to display for the given revision.
        if exit_code == 128:
            return
        elif exit_code != 0:
            raise SourceError("{plugin}: Failed to show gitmodules at ref {ref}".format(plugin=self, ref=self.ref))

        content = "\n".join([l.strip() for l in output.splitlines()])

        io = StringIO(content)
        parser = RawConfigParser()
        parser.read_file(io)

        for section in parser.sections():
            # validate section name against the 'submodule "foo"' pattern
            if re.match(r'submodule "(.*)"', section):
                path = parser.get(section, "path")
                url = parser.get(section, "url")

                yield (path, url)

    # Fetch the ref which this mirror requires its submodule to have,
    # at the given ref of this mirror.
    def submodule_ref(self, submodule, ref=None):
        if not ref:
            ref = self.ref

        # list objects in the parent repo tree to find the commit
        # object that corresponds to the submodule
        _, output = self.source.check_output(
            [self.source.host_git, "ls-tree", ref, submodule],
            fail="ls-tree failed for commit {} and submodule: {}".format(ref, submodule),
            cwd=self.mirror,
        )

        # read the commit hash from the output
        fields = output.split()
        if len(fields) >= 2 and fields[1] == "commit":
            submodule_commit = output.split()[2]

            # fail if the commit hash is invalid
            if len(submodule_commit) != 40:
                raise SourceError(
                    "{}: Error reading commit information for submodule '{}'".format(self.source, submodule)
                )

            return submodule_commit

        else:
            detail = (
                "The submodule '{}' is defined either in the BuildStream source\n".format(submodule)
                + "definition, or in a .gitmodules file. But the submodule was never added to the\n"
                + "underlying git repository with `git submodule add`."
            )

            self.source.warn(
                "{}: Ignoring inconsistent submodule '{}'".format(self.source, submodule),
                detail=detail,
                warning_token=WARN_INCONSISTENT_SUBMODULE,
            )

            return None

    def _rebuild_git(self, fullpath):
        if not self.tags:
            return

        with self.source.tempdir() as tmpdir:
            included = set()
            shallow = set()
            for _, commit_ref, _ in self.tags:

                if commit_ref == self.ref:
                    # rev-list does not work in case of same rev
                    shallow.add(self.ref)
                else:
                    _, out = self.source.check_output(
                        [
                            self.source.host_git,
                            "rev-list",
                            "--ancestry-path",
                            "--boundary",
                            "{}..{}".format(commit_ref, self.ref),
                        ],
                        fail="Failed to get git history {}..{} in directory: {}".format(
                            commit_ref, self.ref, fullpath
                        ),
                        fail_temporarily=True,
                        cwd=self.mirror,
                    )
                    self.source.warn("refs {}..{}: {}".format(commit_ref, self.ref, out.splitlines()))
                    for line in out.splitlines():
                        rev = line.lstrip("-")
                        if line[0] == "-":
                            shallow.add(rev)
                        else:
                            included.add(rev)

            shallow -= included
            included |= shallow

            self.source.call(
                [self.source.host_git, "init"],
                fail="Cannot initialize git repository: {}".format(fullpath),
                cwd=fullpath,
            )

            for rev in included:
                with TemporaryFile(dir=tmpdir) as commit_file:
                    self.source.call(
                        [self.source.host_git, "cat-file", "commit", rev],
                        stdout=commit_file,
                        fail="Failed to get commit {}".format(rev),
                        cwd=self.mirror,
                    )
                    commit_file.seek(0, 0)
                    self.source.call(
                        [self.source.host_git, "hash-object", "-w", "-t", "commit", "--stdin"],
                        stdin=commit_file,
                        fail="Failed to add commit object {}".format(rev),
                        cwd=fullpath,
                    )

            with open(os.path.join(fullpath, ".git", "shallow"), "w") as shallow_file:
                for rev in shallow:
                    shallow_file.write("{}\n".format(rev))

            for tag, commit_ref, annotated in self.tags:
                if annotated:
                    with TemporaryFile(dir=tmpdir) as tag_file:
                        tag_data = "object {}\ntype commit\ntag {}\n".format(commit_ref, tag)
                        tag_file.write(tag_data.encode("ascii"))
                        tag_file.seek(0, 0)
                        _, tag_ref = self.source.check_output(
                            [self.source.host_git, "hash-object", "-w", "-t", "tag", "--stdin"],
                            stdin=tag_file,
                            fail="Failed to add tag object {}".format(tag),
                            cwd=fullpath,
                        )

                    self.source.call(
                        [self.source.host_git, "tag", tag, tag_ref.strip()],
                        fail="Failed to tag: {}".format(tag),
                        cwd=fullpath,
                    )
                else:
                    self.source.call(
                        [self.source.host_git, "tag", tag, commit_ref],
                        fail="Failed to tag: {}".format(tag),
                        cwd=fullpath,
                    )

            with open(os.path.join(fullpath, ".git", "HEAD"), "w") as head:
                self.source.call(
                    [self.source.host_git, "rev-parse", self.ref],
                    stdout=head,
                    fail="Failed to parse commit {}".format(self.ref),
                    cwd=self.mirror,
                )


class _GitSourceBase(Source):
    # pylint: disable=attribute-defined-outside-init

    # The GitMirror class which this plugin uses. This may be
    # overridden in derived plugins as long as the replacement class
    # follows the same interface used by the _GitMirror class
    BST_MIRROR_CLASS = _GitMirror

    def configure(self, node):
        ref = node.get_str("ref", None)

        config_keys = ["url", "track", "ref", "submodules", "checkout-submodules", "ref-format", "track-tags", "tags"]
        node.validate_keys(config_keys + Source.COMMON_CONFIG_KEYS)

        tags_node = node.get_sequence("tags", [])
        for tag_node in tags_node:
            tag_node.validate_keys(["tag", "commit", "annotated"])

        tags = self._load_tags(node)
        self.track_tags = node.get_bool("track-tags", default=False)

        self.original_url = node.get_str("url")
        self.mirror = self.BST_MIRROR_CLASS(self, "", self.original_url, ref, tags=tags, primary=True)
        self.tracking = node.get_str("track", None)

        self.ref_format = node.get_enum("ref-format", _RefFormat, _RefFormat.SHA1)

        # At this point we now know if the source has a ref and/or a track.
        # If it is missing both then we will be unable to track or build.
        if self.mirror.ref is None and self.tracking is None:
            raise SourceError(
                "{}: Git sources require a ref and/or track".format(self), reason="missing-track-and-ref"
            )

        self.checkout_submodules = node.get_bool("checkout-submodules", default=True)

        # Parse a dict of submodule overrides, stored in the submodule_overrides
        # and submodule_checkout_overrides dictionaries.
        self.submodule_overrides = {}
        self.submodule_checkout_overrides = {}
        modules = node.get_mapping("submodules", {})
        for path in modules.keys():
            submodule = modules.get_mapping(path)
            url = submodule.get_str("url", None)

            # Make sure to mark all URLs that are specified in the configuration
            if url:
                self.mark_download_url(url, primary=False)

            self.submodule_overrides[path] = url
            if "checkout" in submodule:
                checkout = submodule.get_bool("checkout")
                self.submodule_checkout_overrides[path] = checkout

        self.mark_download_url(self.original_url)

    def preflight(self):
        # Check if git is installed, get the binary at the same time
        self.host_git = utils.get_host_tool("git")

    def get_unique_key(self):
        ref = self.mirror.ref
        if ref is not None:
            # If the ref contains "-g" (is in git-describe format),
            # only choose the part after, which is the commit ID
            ref = ref.split("-g")[-1]

        # Here we want to encode the local name of the repository and
        # the ref, if the user changes the alias to fetch the same sources
        # from another location, it should not affect the cache key.
        key = [self.original_url, ref]
        if self.mirror.tags:
            tags = {tag: (commit, annotated) for tag, commit, annotated in self.mirror.tags}
            key.append({"tags": tags})

        # Only modify the cache key with checkout_submodules if it's something
        # other than the default behaviour.
        if self.checkout_submodules is False:
            key.append({"checkout_submodules": self.checkout_submodules})

        # We want the cache key to change if the source was
        # configured differently, and submodules count.
        if self.submodule_overrides:
            key.append(self.submodule_overrides)

        if self.submodule_checkout_overrides:
            key.append({"submodule_checkout_overrides": self.submodule_checkout_overrides})

        return key

    def get_consistency(self):
        if self._have_all_refs():
            return Consistency.CACHED
        elif self.mirror.ref is not None:
            return Consistency.RESOLVED
        return Consistency.INCONSISTENT

    def load_ref(self, node):
        self.mirror.ref = node.get_str("ref", None)
        self.mirror.tags = self._load_tags(node)

    def get_ref(self):
        if self.mirror.ref is None:
            return None
        return self.mirror.ref, self.mirror.tags

    def set_ref(self, ref, node):
        if not ref:
            self.mirror.ref = None
            if "ref" in node:
                del node["ref"]
            self.mirror.tags = []
            if "tags" in node:
                del node["tags"]
        else:
            actual_ref, tags = ref
            node["ref"] = self.mirror.ref = actual_ref
            self.mirror.tags = tags
            if tags:
                node["tags"] = []
                for tag, commit_ref, annotated in tags:
                    data = {"tag": tag, "commit": commit_ref, "annotated": annotated}
                    node["tags"].append(data)
            else:
                if "tags" in node:
                    del node["tags"]

    def track(self):  # pylint: disable=arguments-differ

        # If self.tracking is not specified it's not an error, just silently return
        if not self.tracking:
            # Is there a better way to check if a ref is given.
            if self.mirror.ref is None:
                detail = "Without a tracking branch ref can not be updated. Please " + "provide a ref or a track."
                raise SourceError("{}: No track or ref".format(self), detail=detail, reason="track-attempt-no-track")
            return None

        # Resolve the URL for the message
        resolved_url = self.translate_url(self.mirror.url)
        with self.timed_activity("Tracking {} from {}".format(self.tracking, resolved_url), silent_nested=True):
            self.mirror._fetch(resolved_url)

            ref = self.mirror.latest_commit(self.tracking)
            tags = self.mirror.reachable_tags(ref) if self.track_tags else []
            if self.ref_format == _RefFormat.GIT_DESCRIBE:
                ref = self.mirror.describe(ref)

            return ref, tags

    def init_workspace(self, directory):
        with self.timed_activity('Setting up workspace "{}"'.format(directory), silent_nested=True):
            self.mirror.init_workspace(directory)
            for mirror in self._recurse_submodules(configure=True):
                mirror.init_workspace(directory)

    def stage(self, directory):
        # Stage the main repo in the specified directory
        #
        with self.timed_activity("Staging {}".format(self.mirror.url), silent_nested=True):
            self.mirror.stage(directory)
            for mirror in self._recurse_submodules(configure=True):
                mirror.stage(directory)

    def get_source_fetchers(self):
        self.mirror.mark_download_url(self.mirror.url)
        yield self.mirror
        # _recurse_submodules only iterates those which are known at the current
        # cached state - but fetch is called on each result as we go, so this will
        # yield all configured submodules
        for submodule in self._recurse_submodules(configure=True):
            submodule.mark_download_url(submodule.url)
            yield submodule

    def validate_cache(self):
        discovered_submodules = {}
        unlisted_submodules = []
        invalid_submodules = []

        for submodule in self._recurse_submodules(configure=False):
            discovered_submodules[submodule.path] = submodule.url
            if self._ignoring_submodule(submodule.path):
                continue

            if submodule.path not in self.submodule_overrides:
                unlisted_submodules.append((submodule.path, submodule.url))

        # Warn about submodules which are explicitly configured but do not exist
        for path, url in self.submodule_overrides.items():
            if path not in discovered_submodules:
                invalid_submodules.append((path, url))

        if invalid_submodules:
            detail = []
            for path, url in invalid_submodules:
                detail.append("  Submodule URL '{}' at path '{}'".format(url, path))

            self.warn(
                "{}: Invalid submodules specified".format(self),
                warning_token=WARN_INVALID_SUBMODULE,
                detail="The following submodules are specified in the source "
                "description but do not exist according to the repository\n\n" + "\n".join(detail),
            )

        # Warn about submodules which exist but have not been explicitly configured
        if unlisted_submodules:
            detail = []
            for path, url in unlisted_submodules:
                detail.append("  Submodule URL '{}' at path '{}'".format(url, path))

            self.warn(
                "{}: Unlisted submodules exist".format(self),
                warning_token=WARN_UNLISTED_SUBMODULE,
                detail="The following submodules exist but are not specified "
                + "in the source description\n\n"
                + "\n".join(detail),
            )

        # Assert that the ref exists in the track tag/branch, if track has been specified.
        ref_in_track = False
        if self.tracking:
            _, branch = self.check_output(
                [self.host_git, "branch", "--list", self.tracking, "--contains", self.mirror.ref],
                cwd=self.mirror.mirror,
            )
            if branch:
                ref_in_track = True
            else:
                _, tag = self.check_output(
                    [self.host_git, "tag", "--list", self.tracking, "--contains", self.mirror.ref],
                    cwd=self.mirror.mirror,
                )
                if tag:
                    ref_in_track = True

            if not ref_in_track:
                detail = (
                    "The ref provided for the element does not exist locally "
                    + "in the provided track branch / tag '{}'.\n".format(self.tracking)
                    + "You may wish to track the element to update the ref from '{}' ".format(self.tracking)
                    + "with `bst source track`,\n"
                    + "or examine the upstream at '{}' for the specific ref.".format(self.mirror.url)
                )

                self.warn(
                    "{}: expected ref '{}' was not found in given track '{}' for staged repository: '{}'\n".format(
                        self, self.mirror.ref, self.tracking, self.mirror.url
                    ),
                    detail=detail,
                    warning_token=CoreWarnings.REF_NOT_IN_TRACK,
                )

    ###########################################################
    #                     Local Functions                     #
    ###########################################################

    def _have_all_refs(self):
        return self.mirror.has_ref() and all(
            submodule.has_ref() for submodule in self._recurse_submodules(configure=True)
        )

    # _configure_submodules():
    #
    # Args:
    #     submodules: An iterator of _GitMirror (or similar) objects for submodules
    #
    # Returns:
    #     An iterator through `submodules` but filtered of any ignored submodules
    #     and modified to use any custom URLs configured in the source
    #
    def _configure_submodules(self, submodules):
        for submodule in submodules:
            if self._ignoring_submodule(submodule.path):
                continue
            # Allow configuration to override the upstream location of the submodules.
            submodule.url = self.submodule_overrides.get(submodule.path, submodule.url)
            yield submodule

    # _recurse_submodules():
    #
    # Recursively iterates through GitMirrors for submodules of the main repo. Only
    # submodules that are cached are recursed into - but this is decided at
    # iteration time, so you can fetch in a for loop over this function to fetch
    # all submodules.
    #
    # Args:
    #     configure (bool): Whether to apply the 'submodule' config while recursing
    #                       (URL changing and 'checkout' overrides)
    #
    def _recurse_submodules(self, configure):
        def recurse(mirror):
            submodules = mirror.get_submodule_mirrors()
            if configure:
                submodules = self._configure_submodules(submodules)

            for submodule in submodules:
                yield submodule
                if submodule.has_ref():
                    yield from recurse(submodule)

        yield from recurse(self.mirror)

    def _load_tags(self, node):
        tags = []
        tags_node = node.get_sequence("tags", [])
        for tag_node in tags_node:
            tag = tag_node.get_str("tag")
            commit_ref = tag_node.get_str("commit")
            annotated = tag_node.get_bool("annotated")
            tags.append((tag, commit_ref, annotated))
        return tags

    # _ignoring_submodule():
    #
    # Args:
    #     path (str): The path of a submodule in the superproject
    #
    # Returns:
    #     (bool): Whether to not clone/checkout this submodule
    #
    def _ignoring_submodule(self, path):
        return not self.submodule_checkout_overrides.get(path, self.checkout_submodules)
