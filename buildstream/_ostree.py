#
#  Copyright (C) 2017 Codethink Limited
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
#        Andrew Leeming <andrew.leeming@codethink.co.uk>
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#
# Code based on Jürg's artifact cache and Andrew's ostree plugin
#

# Disable pylint warnings that are not appicable to this module
# pylint: disable=bad-exception-context,catching-non-exception

import os

import gi
from gi.repository.GLib import Variant, VariantDict

from ._exceptions import BstError, ErrorDomain

# pylint: disable=wrong-import-position,wrong-import-order
gi.require_version('OSTree', '1.0')
from gi.repository import GLib, Gio, OSTree  # nopep8


# For users of this file, they must expect (except) it.
class OSTreeError(BstError):
    def __init__(self, message, reason=None):
        super().__init__(message, domain=ErrorDomain.UTIL, reason=reason)


# ensure()
#
# Args:
#    path (str): The file path to where the desired repo should be
#    compress (bool): use compression or not when creating
#
# Returns: an OSTree.Repo
def ensure(path, compress):

    # create also succeeds on existing repository
    repo = OSTree.Repo.new(Gio.File.new_for_path(path))
    mode = OSTree.RepoMode.ARCHIVE_Z2 if compress \
        else OSTree.RepoMode.BARE_USER

    repo.create(mode)

    # Disble OSTree's built in minimum-disk-space check.
    config = repo.copy_config()
    config.set_string('core', 'min-free-space-percent', '0')
    repo.write_config(config)
    repo.reload_config()

    return repo


# checkout()
#
# Checkout the content at 'commit' from 'repo' in
# the specified 'path'
#
# Args:
#    repo (OSTree.Repo): The repo
#    path (str): The checkout path
#    commit_ (str): The commit checksum to checkout
#    user (boot): Whether to checkout in user mode
#
def checkout(repo, path, commit_, user=False):

    # Check out a full copy of an OSTree at a given ref to some directory.
    #
    # Note: OSTree does not like updating directories inline/sync, therefore
    # make sure you checkout to a clean directory or add additional code to support
    # union mode or (if it exists) file replacement/update.
    #
    # Returns True on success
    #
    # cli exmaple:
    #   ostree --repo=repo checkout --user-mode runtime/org.freedesktop.Sdk/x86_64/1.4 foo
    os.makedirs(os.path.dirname(path), exist_ok=True)

    options = OSTree.RepoCheckoutAtOptions()

    # For repos which contain root owned files, we need
    # to checkout with OSTree.RepoCheckoutMode.USER
    #
    # This will reassign uid/gid and also munge the
    # permission bits a bit.
    if user:
        options.mode = OSTree.RepoCheckoutMode.USER

    # Using AT_FDCWD value from fcntl.h
    #
    # This will be ignored if the passed path is an absolute path,
    # if path is a relative path then it will be appended to the
    # current working directory.
    AT_FDCWD = -100
    try:
        repo.checkout_at(options, AT_FDCWD, path, commit_)
    except GLib.GError as e:
        raise OSTreeError("Failed to checkout commit '{}': {}".format(commit_, e.message)) from e


# exists():
#
# Checks wether a given commit or symbolic ref exists and
# is locally cached in the specified repo.
#
# Args:
#    repo (OSTree.Repo): The repo
#    ref (str): A commit checksum or symbolic ref
#
# Returns:
#    (bool): Whether 'ref' is valid in 'repo'
#
def exists(repo, ref):

    # Get the commit checksum, this will:
    #
    #  o Return a commit checksum if ref is a symbolic branch
    #  o Return the same commit checksum if ref is a valid commit checksum
    #  o Return None if the ostree repo doesnt know this ref.
    #
    ref = checksum(repo, ref)
    if ref is None:
        return False

    # If we do have a ref which the ostree knows about, this does
    # not mean we necessarily have the object locally (we may just
    # have some metadata about it, this can happen).
    #
    # Use has_object() only with a resolved valid commit checksum
    # to check if we actually have the object locally.
    _, has_object = repo.has_object(OSTree.ObjectType.COMMIT, ref, None)
    return has_object


# checksum():
#
# Returns the commit checksum for a given symbolic ref,
# which might be a branch or tag. If it is a branch,
# the latest commit checksum for the given branch is returned.
#
# Args:
#    repo (OSTree.Repo): The repo
#    ref (str): The symbolic ref
#
# Returns:
#    (str): The commit checksum, or None if ref does not exist.
#
def checksum(repo, ref):

    _, checksum_ = repo.resolve_rev(ref, True)
    return checksum_


# fetch()
#
# Fetch new objects from a remote, if configured
#
# Args:
#    repo (OSTree.Repo): The repo
#    remote (str): An optional remote name, defaults to 'origin'
#    ref (str): An optional ref to fetch, will reduce the amount of objects fetched
#    progress (callable): An optional progress callback
#
# Note that a commit checksum or a branch reference are both
# valid options for the 'ref' parameter. Using the ref parameter
# can save a lot of bandwidth but mirroring the full repo is
# still possible.
#
def fetch(repo, remote="origin", ref=None, progress=None):
    # Fetch metadata of the repo from a remote
    #
    # cli example:
    #  ostree --repo=repo pull --mirror freedesktop:runtime/org.freedesktop.Sdk/x86_64/1.4
    def progress_callback(info):
        status = async_progress.get_status()
        outstanding_fetches = async_progress.get_uint('outstanding-fetches')
        bytes_transferred = async_progress.get_uint64('bytes-transferred')
        fetched = async_progress.get_uint('fetched')
        requested = async_progress.get_uint('requested')

        if status:
            progress(0.0, status)
        elif outstanding_fetches > 0:
            formatted_bytes = GLib.format_size_full(bytes_transferred, 0)
            if requested == 0:
                percent = 0.0
            else:
                percent = (fetched * 1.0 / requested) * 100

            progress(percent,
                     "Receiving objects: {:d}% ({:d}/{:d}) {}".format(int(percent), fetched,
                                                                      requested, formatted_bytes))
        else:
            progress(100.0, "Writing Objects")

    async_progress = None
    if progress is not None:
        async_progress = OSTree.AsyncProgress.new()
        async_progress.connect('changed', progress_callback)

    # FIXME: This hangs the process and ignores keyboard interrupt,
    #        fix this using the Gio.Cancellable
    refs = None
    if ref is not None:
        refs = [ref]

    try:
        repo.pull(remote,
                  refs,
                  OSTree.RepoPullFlags.MIRROR,
                  async_progress,
                  None)  # Gio.Cancellable
    except GLib.GError as e:
        if ref is not None:
            raise OSTreeError("Failed to fetch ref '{}' from '{}': {}".format(ref, remote, e.message)) from e
        else:
            raise OSTreeError("Failed to fetch from '{}': {}".format(remote, e.message)) from e


# configure_remote():
#
# Ensures a remote is setup to a given url.
#
# Args:
#    repo (OSTree.Repo): The repo
#    remote (str): The name of the remote
#    url (str): The url of the remote ostree repo
#    key_url (str): The optional url of a GPG key (should be a local file)
#
def configure_remote(repo, remote, url, key_url=None):
    # Add a remote OSTree repo. If no key is given, we disable gpg checking.
    #
    # cli exmaple:
    #   wget https://sdk.gnome.org/keys/gnome-sdk.gpg
    #   ostree --repo=repo --gpg-import=gnome-sdk.gpg remote add freedesktop https://sdk.gnome.org/repo
    options = None  # or GLib.Variant of type a{sv}
    if key_url is None:
        vd = VariantDict.new()
        vd.insert_value('gpg-verify', Variant.new_boolean(False))
        options = vd.end()

    try:
        repo.remote_change(None,      # Optional OSTree.Sysroot
                           OSTree.RepoRemoteChange.ADD_IF_NOT_EXISTS,
                           remote,    # Remote name
                           url,       # Remote url
                           options,   # Remote options
                           None)      # Optional Gio.Cancellable
    except GLib.GError as e:
        raise OSTreeError("Failed to configure remote '{}': {}".format(remote, e.message)) from e

    # Remote needs to exist before adding key
    if key_url is not None:
        try:
            gfile = Gio.File.new_for_uri(key_url)
            stream = gfile.read()
            repo.remote_gpg_import(remote, stream, None, 0, None)
        except GLib.GError as e:
            raise OSTreeError("Failed to add gpg key from url '{}': {}".format(key_url, e.message)) from e
