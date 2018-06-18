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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
from collections import OrderedDict
from contextlib import contextmanager, ExitStack

from .. import utils
from .._fuse import SafeHardlinks


# Mount()
#
# Helper data object representing a single mount point in the mount map
#
class Mount():
    def __init__(self, sandbox, mount_point, safe_hardlinks):
        scratch_directory = sandbox._get_scratch_directory()
        root_directory = sandbox.get_directory()

        self.mount_point = mount_point
        self.safe_hardlinks = safe_hardlinks

        # FIXME: When the criteria for mounting something and it's parent
        #        mount is identical, then there is no need to mount an additional
        #        fuse layer (i.e. if the root is read-write and there is a directory
        #        marked for staged artifacts directly within the rootfs, they can
        #        safely share the same fuse layer).
        #
        #        In these cases it would be saner to redirect the sub-mount to
        #        a regular mount point within the parent's redirected mount.
        #
        if self.safe_hardlinks:
            # Redirected mount
            self.mount_origin = os.path.join(root_directory, mount_point.lstrip(os.sep))
            self.mount_base = os.path.join(scratch_directory, utils.url_directory_name(mount_point))
            self.mount_source = os.path.join(self.mount_base, 'mount')
            self.mount_tempdir = os.path.join(self.mount_base, 'temp')
            os.makedirs(self.mount_origin, exist_ok=True)
            os.makedirs(self.mount_tempdir, exist_ok=True)
        else:
            # No redirection needed
            self.mount_source = os.path.join(root_directory, mount_point.lstrip(os.sep))

        external_mount_sources = sandbox._get_mount_sources()
        external_mount_source = external_mount_sources.get(mount_point)

        if external_mount_source is None:
            os.makedirs(self.mount_source, exist_ok=True)
        else:
            if os.path.isdir(external_mount_source):
                os.makedirs(self.mount_source, exist_ok=True)
            else:
                # When mounting a regular file, ensure the parent
                # directory exists in the sandbox; and that an empty
                # file is created at the mount location.
                parent_dir = os.path.dirname(self.mount_source.rstrip('/'))
                os.makedirs(parent_dir, exist_ok=True)
                if not os.path.exists(self.mount_source):
                    with open(self.mount_source, 'w'):
                        pass

    @contextmanager
    def mounted(self, sandbox):
        if self.safe_hardlinks:
            mount = SafeHardlinks(self.mount_origin, self.mount_tempdir)
            with mount.mounted(self.mount_source):
                yield
        else:
            # Nothing to mount here
            yield


# MountMap()
#
# Helper object for mapping of the sandbox mountpoints
#
# Args:
#    sandbox (Sandbox): The sandbox object
#    root_readonly (bool): Whether the sandbox root is readonly
#
class MountMap():

    def __init__(self, sandbox, root_readonly):
        # We will be doing the mounts in the order in which they were declared.
        self.mounts = OrderedDict()

        # We want safe hardlinks on rootfs whenever root is not readonly
        self.mounts['/'] = Mount(sandbox, '/', not root_readonly)

        for mark in sandbox._get_marked_directories():
            directory = mark['directory']
            artifact = mark['artifact']

            # We want safe hardlinks for any non-root directory where
            # artifacts will be staged to
            self.mounts[directory] = Mount(sandbox, directory, artifact)

    # get_mount_source()
    #
    # Gets the host directory where the mountpoint in the
    # sandbox should be bind mounted from
    #
    # Args:
    #    mountpoint (str): The absolute mountpoint path inside the sandbox
    #
    # Returns:
    #    The host path to be mounted at the mount point
    #
    def get_mount_source(self, mountpoint):
        return self.mounts[mountpoint].mount_source

    # mounted()
    #
    # A context manager which ensures all the mount sources
    # were mounted with any fuse layers which may have been needed.
    #
    # Args:
    #    sandbox (Sandbox): The sandbox
    #
    @contextmanager
    def mounted(self, sandbox):
        with ExitStack() as stack:
            for _, mount in self.mounts.items():
                stack.enter_context(mount.mounted(sandbox))
            yield
