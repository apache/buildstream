# Profile helper for the SafeHardlinks FUSE filesystem
#
# Run this from a project directory and pass it the name of an element to
# stage.
#
# It will stage the artifact and then block the main process. At this point
# you can open a bwrap sandbox and run a command inside the FUSE mount
# manually. Once you are done, hit CTRL+C and a profile will be written to
# disk of what happened inside the FUSE mount.


import cProfile
import os
import signal
import subprocess
import sys
import tempfile

import buildstream
import buildstream._frontend


# This works by monkeypatching the .mount() method on the SafeHardlinks
# filesystem. The normal implementation in the _fuse.mount module spawns
# a multiprocessing.Process subprocess to actually run the filesystem
# and the main process carries on independently. We override that so that
# it blocks
def mount_in_process_and_block(self, mountpoint):
    self._Mount__mountpoint = mountpoint

    self._Mount__operations = self.create_operations()

    profile = os.path.abspath('fuse.pstats')

    print("Mounting a SafeHardlinks filesystem at {} then blocking".format(mountpoint))
    print("Profile will be written to {}".format(profile))
    print("Try: bwrap --bind {} / --dev /dev --proc /proc --tmpfs /tmp COMMAND".format(mountpoint))

    profiler = cProfile.Profile()
    profiler.runcall(
        buildstream._fuse.fuse.FUSE,
        self._Mount__operations, self._Mount__mountpoint,
        nothreads=True, foreground=True, nonempty=True)
    profiler.dump_stats(profile)


buildstream._fuse.hardlinks.SafeHardlinks.mount = mount_in_process_and_block


if len(sys.argv) != 2:
    raise RuntimeError("Usage: {} ELEMENT".format(sys.argv[0]))

element = sys.argv[1]


cli = buildstream._frontend.main.cli
cli.main(args=('shell', element), prog_name=cli.name)
