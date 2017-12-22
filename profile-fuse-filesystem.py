# Profile helper for the SafeHardlinks FUSE filesystem
#
# Run inside a project directory!


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

    print("Mounting a SafeHardlinks filesystem at {} then blocking".format(mountpoint))
    print("Profile will be written to {}".format(os.path.abspath('fuse.pstats')))
    print("Try: bwrap --bind {} / --dev /dev --proc /proc --tmpfs /tmp COMMAND".format(mountpoint))

    with tempfile.NamedTemporaryFile('w') as f:
        f.write("""
import buildstream, sys\n
operations = buildstream._fuse.hardlinks.SafeHardlinkOps(sys.argv[2], sys.argv[3])\n
buildstream._fuse.fuse.FUSE(operations, sys.argv[1], nothreads=True, foreground=True, nonempty=True)\n
        """)
        f.flush()

        args = [sys.executable, '-m', 'cProfile',  f.name,
                mountpoint, self.directory, self.tempdir]
        print(args)

        # Run the FUSE mount as subprocess with profiling enabled.
        try:
            p = subprocess.Popen(args)
            p.wait()
        except KeyboardInterrupt:
            print("Terminating on KeyboardInterrupt")
            p.send_signal(signal.SIGINT)
            p.wait()
            print("Returncode: {}".format(p.returncode))
            raise


    # Here's how you'd run the FUSE mount in-process. Your profile gets skewed
    # by the time spent staging stuff though.
    #buildstream._fuse.fuse.FUSE(self._Mount__operations,
    #                            self._Mount__mountpoint,
    #                            nothreads=True, foreground=True, nonempty=True)


buildstream._fuse.hardlinks.SafeHardlinks.mount = mount_in_process_and_block


if len(sys.argv) != 2:
    raise RuntimeError("Usage: {} ELEMENT".format(sys.argv[0]))

element = sys.argv[1]


cli = buildstream._frontend.main.cli
cli.main(args=('shell', element), prog_name=cli.name)
