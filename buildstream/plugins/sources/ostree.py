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

from gi.repository import OSTree, Gio
from buildstream import Source, LoadError


class OSTreeSource(Source):

    def configure(self, node):
        project = self.get_project()

        self.remote_name = "origin"
        self.url = project.translate_url(self.node_get_member(node, str, 'url'))
        self.ref = self.node_get_member(node, str, 'ref')
        self.track = self.node_get_member(node, str, 'track', '')

        # (optional) Not all repos are signed. But if they are, get the gpg key
        try:
            self.gpg_key = self.node_get_member(node, str, 'gpg_key', None)
        except LoadError:
            self.gpg_key = None

        self.ostree_dir = "repo"    # Assume to be some tmp dir

    def preflight(self):
        return

    def get_unique_key(self):
        return [self.url, self.ref]

    def refresh(self, node):
        # Not sure what else to put here

        self.load_ostree(self.ostree_dir)
        self.fetch_ostree(self.remote_name, self.ref)

        # TODO Only return true if things have been updated. Not sure
        # how I'd do this with OSTree. Surely the ref used means nothing
        # is different, unless this has not been pulled yet.
        return True

    def fetch(self):
        # Pull the OSTree from the remote

        self.init_ostree(self.ostree_dir, self.remote_name, self.url)
        self.fetch_ostree(self.remote_name, self.ref)

    def stage(self, directory):
        # Checkout self.ref into the specified directory

        self.checkout_ostree(directory, self.ref)
        pass

    def consistent(self):
        return True

    ###########################################################
    #                     Local Functions                     #
    ###########################################################

    def init_ostree(self, repo_dir, remote_name, remote_url):
        # Initialises a new empty OSTree repo
        # ostree --repo=repo init --mode=archive-z2

        self.ost = OSTree.Repo.new(Gio.File.new_for_path(repo_dir))
        self.ost.create(OSTree.RepoMode.ARCHIVE_Z2, None)
        self.add_remote(remote_name, remote_url)

    def load_ostree(self, repo_dir):
        # Loads an existing OSTree repo from the given `repo_dir`

        self.ost = OSTree.Repo.new(Gio.File.new_for_path(repo_dir))
        self.ost.open()

    def fetch_ostree(self, remote, ref):
        # ostree --repo=repo pull --mirror freedesktop:runtime/org.freedesktop.Sdk/x86_64/1.4

        progress = None  # Alternatively OSTree.AsyncProgress, None assumed to block
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

    def ls_tracks(self):
        # Grab the named refs/tracks that exist in this repo
        # ostree --repo=repo refs
        _, refs = self.ost.list_refs()

        # Returns a dict of {branch: head-ref}
        return refs.keys()

    def track_head(self, track_name):
        # Get the checksum of the head commit of the branch `track_name`
        # ostree --repo=repo log runtime/org.freedesktop.Sdk/x86_64/1.4
        _, head_ref = self.ost.resolve_ref(track_name)

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
