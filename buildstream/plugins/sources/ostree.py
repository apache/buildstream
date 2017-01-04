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
#        Andrew Leeming <andrew.leeming@codethink.co.uk>

"""A Source implementation for OSTree based directory artifacts

"""

import os
import subprocess
from gi.repository import OSTree, Gio

from buildstream import Source, SourceError, ProgramNotFoundError
from buildstream import utils


class OSTreeSource(Source):

    def configure(self, node):
        self.remote_name = "origin"
        self.url = utils.node_get_member(node, str, 'url')
        self.ref = utils.node_get_member(node, str, 'ref', '')
        self.branch = utils.node_get_member(node, str, 'branch', '')

        # (optional) Not all repos are signed. But if they are, get the gpg key
        self.gpg_key = utils.node_get_member(node, str, 'gpg_key', None)

        self.ostree_dir = "repo"    # Assume to be some tmp dir

    def preflight(self):
        # Check if OSTree is installed, get the binary at the same time
        # TODO Actually, this isn't needed due to python bindings?
        try:
            self.host_ostree = utils.get_host_tool("ostree")
        except ProgramNotFoundError as e:
            raise SourceError("Prerequisite programs not found in host environment for OSTree", e)

    def get_unique_key(self):
        return [self.url, self.ref]

    def refresh(self, node):
        # Not sure what to put here

        self.load_ostree(self.ostree_dir)
        self.fetch_ostree(self.remote_name, self.ref)

    def fetch(self):
        # Pull the OSTree from the remote

        self.init_ostree(self.ostree_dir)
        self.fetch_ostree(self.remote_name, self.ref)

    def stage(self, directory):
        # Checkout self.ref into the specified directory

        self.checkout_ostree(directory, self.ref)
        pass

    ###########################################################
    #                     Local Functions                     #
    ###########################################################

    def init_ostree(self, repo_dir):
        # Initialises a new empty OSTree repo
        # ostree --repo=repo init --mode=archive-z2

        self.ost = OSTree.Repo.new(Gio.File.new_for_path(repo_dir))
        self.ost.create(OSTree.RepoMode.ARCHIVE_Z2 , None)

    def load_ostree(self, repo_dir):
        # Loads an existing OSTree repo from the given `repo_dir`

        self.ost = OSTree.Repo.new(Gio.File.new_for_path(repo_dir))
        self.ost.open()

    def fetch_ostree(self, remote, ref):
        # ostree --repo=repo pull --mirror freedesktop:runtime/org.freedesktop.Sdk/x86_64/1.4

        progress = None  # Alternatively OSTree.AsyncProgress
        cancellable = None  # Alternatively Gio.Cancellable

        self.ost.pull(remote, ref, OSTree.RepoPullFlags.MIRROR, progress, cancellable)

    def add_remote(self, name, url, key=None):
        options = None  # or GLib.Variant of type a{sv}
        cancellable = None  # or Gio.Cancellable

        self.ost.remote_add(name, url, options, cancellable)

        # Remote needs to exist before adding key
        if key is not None:
            self.add_pgp_key(name, key)

    def add_pgp_key(self, name, url):
        # wget https://sdk.gnome.org/keys/gnome-sdk.gpg
        # ostree --repo=repo --gpg-import=gnome-sdk.gpg remote add freedesktop https://sdk.gnome.org/repo

        gfile = Gio.File.new_for_uri(url)
        stream = gfile.read()

        self.ost.remote_gpg_import(name, stream, None, 0, None)
        return

    def ls_branches(self):
        # Grab the named refs/branches that exist in this repo
        # ostree --repo=repo refs
        _, refs = self.ost.list_refs()

        # Returns a dict of {branch: head-ref}
        return refs.keys()

    def branch_head(self, branch_name):
        # Get the checksum of the head commit of the branch `branch_name`
        # ostree --repo=repo log runtime/org.freedesktop.Sdk/x86_64/1.4
        _, head_ref = self.ost.resolve_ref(branch_name)

        return head_ref

    def ls_files(self, ref):
        # ostree --repo=repo ls -R 6fe05489235bcae562f0afa5aca9bb8d350bdf93ea8f4645adb694b907f48190
        pass

    def checkout_ostree(self, checkout_dir, ref):
        # ostree --repo=repo checkout --user-mode runtime/org.freedesktop.Sdk/x86_64/1.4 foo

        options = OSTree.RepoCheckoutAtOptions()
        # ignore uid/gid to allow checkout as non-root
        options.mode = OSTree.RepoCheckoutMode.USER

        # from fcntl.h
        AT_FDCWD = -100
        self.repo.checkout_at(options, AT_FDCWD, checkout_dir, ref)


# Plugin entry point
def setup():
    return OSTreeSource
