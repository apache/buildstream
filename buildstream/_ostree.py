#!/usr/bin/env python3
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
from collections import namedtuple

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


# commit():
#
# Commit built artifact to cache.
#
# Files are all recorded with uid/gid 0
#
# Args:
#    repo (OSTree.Repo): The repo
#    dir_ (str): The source directory to commit to the repo
#    refs (list): A list of symbolic references (tag) for the commit
#
def commit(repo, dir_, refs):

    def commit_filter(repo, path, file_info):

        # For now, just set everything in the repo as uid/gid 0
        #
        # In the future we'll want to extract virtualized file
        # attributes from a fuse layer and use that.
        #
        file_info.set_attribute_uint32('unix::uid', 0)
        file_info.set_attribute_uint32('unix::gid', 0)

        return OSTree.RepoCommitFilterResult.ALLOW

    commit_modifier = OSTree.RepoCommitModifier.new(
        OSTree.RepoCommitModifierFlags.NONE, commit_filter)

    repo.prepare_transaction()
    try:
        # add tree to repository
        mtree = OSTree.MutableTree.new()
        repo.write_directory_to_mtree(Gio.File.new_for_path(dir_),
                                      mtree, commit_modifier)
        _, root = repo.write_mtree(mtree)

        # create root commit object, no parent, no branch
        _, rev = repo.write_commit(None, None, None, None, root)

        # create refs
        for ref in refs:
            repo.transaction_set_ref(None, ref, rev)

        # complete repo transaction
        repo.commit_transaction(None)
    except GLib.GError as e:

        # Reraise any error as a buildstream error
        repo.abort_transaction()
        raise OSTreeError(e.message) from e


# set_ref():
#
# Set symbolic reference to specified revision.
#
# Args:
#    repo (OSTree.Repo): The repo
#    ref (str): A symbolic reference (tag) for the commit
#    rev (str): Commit checksum
#
def set_ref(repo, ref, rev):

    repo.prepare_transaction()
    try:
        repo.transaction_set_ref(None, ref, rev)

        # complete repo transaction
        repo.commit_transaction(None)
    except:
        repo.abort_transaction()
        raise


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


OSTREE_GIO_FAST_QUERYINFO = ("standard::name,standard::type,standard::size,"
                             "standard::is-symlink,standard::symlink-target,"
                             "unix::device,unix::inode,unix::mode,unix::uid,"
                             "unix::gid,unix::rdev")


DiffItem = namedtuple('DiffItem', ['src', 'src_info',
                                   'target', 'target_info',
                                   'src_checksum', 'target_checksum'])


# diff_dirs():
#
# Compute the difference between directory a and b as 3 separate sets
# of OSTree.DiffItem.
#
# This is more-or-less a direct port of OSTree.diff_dirs (which cannot
# be used via PyGobject), but does not support options.
#
# Args:
#    a (Gio.File): The first directory for the comparison.
#    b (Gio.File): The second directory for the comparison.
#
# Returns:
#    (modified, removed, added)
#
def diff_dirs(a, b):
    # get_file_checksum():
    #
    # Helper to compute the checksum of an arbitrary file (different
    # objects have different methods to compute these).
    #
    def get_file_checksum(f, f_info):
        if isinstance(f, OSTree.RepoFile):
            return f.get_checksum()
        else:
            contents = None
            if f_info.get_file_type() == Gio.FileType.REGULAR:
                contents = f.read()

            csum = OSTree.checksum_file_from_input(f_info, None, contents,
                                                   OSTree.ObjectType.FILE)
            return OSTree.checksum_from_bytes(csum)

    # diff_files():
    #
    # Helper to compute a diff between two files.
    #
    def diff_files(a, a_info, b, b_info):
        checksum_a = get_file_checksum(a, a_info)
        checksum_b = get_file_checksum(b, b_info)

        if checksum_a != checksum_b:
            return DiffItem(a, a_info, b, b_info, checksum_a, checksum_b)

        return None

    # diff_add_dir_recurse():
    #
    # Helper to collect all files in a directory recursively.
    #
    def diff_add_dir_recurse(d):
        added = []

        dir_enum = d.enumerate_children(OSTREE_GIO_FAST_QUERYINFO,
                                        Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)

        for child_info in dir_enum:
            name = child_info.get_name()
            child = d.get_child(name)
            added.append(child)

            if child_info.get_file_type() == Gio.FileType.DIRECTORY:
                added.extend(diff_add_dir_recurse(child))

        return added

    modified = []
    removed = []
    added = []

    child_a_info = a.query_info(OSTREE_GIO_FAST_QUERYINFO,
                                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)
    child_b_info = b.query_info(OSTREE_GIO_FAST_QUERYINFO,
                                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)

    # If both are directories and have the same checksum, we know that
    # none of the underlying files changed, so we can save time.
    if (child_a_info.get_file_type() == Gio.FileType.DIRECTORY and
            child_b_info.get_file_type() == Gio.FileType.DIRECTORY and
            isinstance(a, OSTree.RepoFileClass) and
            isinstance(b, OSTree.RepoFileClass)):
        if a.tree_get_contents_checksum() == b.tree_get_contents_checksum():
            return modified, removed, added

    # We walk through 'a' first
    dir_enum = a.enumerate_children(OSTREE_GIO_FAST_QUERYINFO,
                                    Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)
    for child_a_info in dir_enum:
        name = child_a_info.get_name()

        child_a = a.get_child(name)
        child_a_type = child_a_info.get_file_type()

        try:
            child_b = b.get_child(name)
            child_b_info = child_b.query_info(OSTREE_GIO_FAST_QUERYINFO,
                                              Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)
        except GLib.Error as e:
            # If the file does not exist in b, it has been removed
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_FOUND):
                removed.append(child_a)
                continue
            else:
                raise

        # If the files differ but are of different types, we report a
        # modification, saving a bit of time because we won't need a
        # checksum
        child_b_type = child_b_info.get_file_type()
        if child_a_type != child_b_type:
            diff_item = DiffItem(child_a, child_a_info,
                                 child_b, child_b_info,
                                 None, None)
            modified.append(diff_item)
        # Finally, we compute checksums and compare the file contents directly
        else:
            diff_item = diff_files(child_a, child_a_info, child_b, child_b_info)

            if diff_item:
                modified.append(diff_item)

            # If the files are both directories, we recursively use
            # this function to find differences - saving time if they
            # are equal.
            if child_a_type == Gio.FileType.DIRECTORY:
                subdir = diff_dirs(child_a, child_b)
                modified.extend(subdir[0])
                removed.extend(subdir[1])
                added.extend(subdir[2])

    # Now we walk through 'b' to find any files that were added
    dir_enum = b.enumerate_children(OSTREE_GIO_FAST_QUERYINFO,
                                    Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)
    for child_b_info in dir_enum:
        name = child_b_info.get_name()

        child_b = b.get_child(name)

        try:
            child_a = a.get_child(name)
            child_a_info = child_a.query_info(OSTREE_GIO_FAST_QUERYINFO,
                                              Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS)
        except GLib.Error as e:
            # If the file does not exist in 'a', it was added.
            if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.NOT_FOUND):
                added.append(child_b)
                if child_b_info.get_file_type() == Gio.FileType.DIRECTORY:
                    added.extend(diff_add_dir_recurse(child_b))
                continue
            else:
                raise

    return modified, removed, added


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
