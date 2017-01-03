#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

import os
import tempfile
import gi
gi.require_version('OSTree', '1.0')
from gi.repository import GLib, Gio, OSTree  # nopep8


def buildref(project, element, key):
    # assume project and element names are not allowed to contain slashes
    return '{0}/{1}/{2}'.format(project, element, key)


# An ArtifactCache manages artifacts in an OSTree repository
#
# Args:
#     context (Context): The BuildStream context
#
class ArtifactCache():
    def __init__(self, context):

        self.context = context

        os.makedirs(context.artifactdir, exist_ok=True)
        ostreedir = os.path.join(context.artifactdir, 'ostree')
        self.extractdir = os.path.join(context.artifactdir, 'extract')

        self.repo = OSTree.Repo.new(Gio.File.new_for_path(ostreedir))

        # create also succeeds on existing repository
        self.repo.create(OSTree.RepoMode.BARE_USER)

        # construct commit filter that resets file ownership
        self.commit_modifier = OSTree.RepoCommitModifier.new(
            OSTree.RepoCommitModifierFlags.NONE,
            self.commit_filter)

    def commit_filter(self, repo, path, file_info):
        # force uid and gid to 0
        file_info.set_attribute_uint32('unix::uid', 0)
        file_info.set_attribute_uint32('unix::gid', 0)

        return OSTree.RepoCommitFilterResult.ALLOW

    # contains():
    #
    # Check whether the specified artifact is already available in the
    # local artifact cache.
    #
    # Args:
    #     project (str): The name of the project
    #     element (str): The name of the element
    #     key (str):     The cache key
    #
    # Returns: True if the artifact is in the cache, False otherwise
    #
    def contains(self, project, element, key):
        ref = buildref(project, element, key)

        # check whether the ref is already available locally
        _, rev = self.repo.resolve_rev(ref, True)
        return rev is not None

    # extract():
    #
    # Extract cached artifact if it hasn't already been extracted.
    # Assumes artifact has previously been fetched or committed.
    #
    # Args:
    #     project (str): The name of the project
    #     element (str): The name of the element
    #     key (str):     The cache key
    #
    # Returns: path to extracted artifact
    #
    def extract(self, project, element, key):
        ref = buildref(project, element, key)

        dest = os.path.join(self.extractdir, ref)
        if os.path.isdir(dest):
            # artifact has already been extracted
            return dest

        # resolve ref to checksum
        _, rev = self.repo.resolve_rev(ref, False)

        os.makedirs(self.extractdir, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='tmp', dir=self.extractdir) as tmpdir:

            checkoutdir = os.path.join(tmpdir, ref)
            os.makedirs(os.path.dirname(checkoutdir))

            options = OSTree.RepoCheckoutAtOptions()
            # ignore uid/gid to allow checkout as non-root
            options.mode = OSTree.RepoCheckoutMode.USER

            # from fcntl.h
            AT_FDCWD = -100
            self.repo.checkout_at(options, AT_FDCWD, checkoutdir, rev)

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                os.rename(checkoutdir, dest)
            except OSError as e:
                if e.errno != os.errno.ENOTEMPTY:
                    raise
                # If rename fails with ENOTEMPTY, another process beat
                # us to it. This is no issue.

        return dest

    # commit():
    #
    # Commit built artifact to cache.
    #
    # Args:
    #     project (str): The name of the project
    #     element (str): The name of the element
    #     key (str):     The cache key
    #     dir (str):     The source directory
    #
    def commit(self, project, element, key, dir):
        ref = buildref(project, element, key)

        self.repo.prepare_transaction()
        try:
            # add tree to repository
            mtree = OSTree.MutableTree.new()
            self.repo.write_directory_to_mtree(Gio.File.new_for_path(dir),
                                               mtree, self.commit_modifier)
            _, root = self.repo.write_mtree(mtree)

            # create root commit object, no parent, no branch
            _, rev = self.repo.write_commit(None, ref, None, None, root)

            # create tag
            self.repo.transaction_set_ref(None, ref, rev)

            # complete repo transaction
            self.repo.commit_transaction(None)
        except:
            self.repo.abort_transaction()
            raise
