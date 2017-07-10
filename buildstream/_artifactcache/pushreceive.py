#!/usr/bin/python3

# Push OSTree commits to a remote repo, based on Dan Nicholson's ostree-push
#
# Copyright (C) 2015  Dan Nicholson <nicholson@endlessm.com>
# Copyright (C) 2017  Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from argparse import ArgumentParser
from enum import Enum
import logging
import os
import struct
import subprocess
import sys
import tempfile
import shutil
import tarfile
import signal
from urllib.parse import urlparse

from .. import _signals

import gi
gi.require_version('OSTree', '1.0')
from gi.repository import GLib, Gio, OSTree  # nopep8


PROTO_VERSION = 0
HEADER_SIZE = 5


# An error occurred
class PushException(Exception):
    pass


# Trying to commit a ref which already exists in remote
class PushExistsException(Exception):
    pass


class PushCommandType(Enum):
    info = 0
    update = 1
    putobjects = 2
    status = 3
    done = 4


def msg_byteorder(sys_byteorder=sys.byteorder):
    if sys_byteorder == 'little':
        return 'l'
    elif sys_byteorder == 'big':
        return 'B'
    else:
        raise PushException('Unrecognized system byteorder %s'
                            % sys_byteorder)


def sys_byteorder(msg_byteorder):
    if msg_byteorder == 'l':
        return 'little'
    elif msg_byteorder == 'B':
        return 'big'
    else:
        raise PushException('Unrecognized message byteorder %s'
                            % msg_byteorder)


def ostree_object_path(repo, obj):
    repodir = repo.get_path().get_path()
    return os.path.join(repodir, 'objects', obj[0:2], obj[2:])


class PushCommand(object):
    def __init__(self, cmdtype, args):
        self.cmdtype = cmdtype
        self.args = args
        self.validate(self.cmdtype, self.args)
        self.variant = GLib.Variant('a{sv}', self.args)

    @staticmethod
    def validate(command, args):
        if not isinstance(command, PushCommandType):
            raise PushException('Message command must be PushCommandType')
        if not isinstance(args, dict):
            raise PushException('Message args must be dict')
        # Ensure all values are variants for a{sv} vardict
        for val in args.values():
            if not isinstance(val, GLib.Variant):
                raise PushException('Message args values must be '
                                    'GLib.Variant')


class PushMessageWriter(object):
    def __init__(self, file, byteorder=sys.byteorder):
        self.file = file
        self.byteorder = byteorder
        self.msg_byteorder = msg_byteorder(self.byteorder)

    def encode_header(self, cmdtype, size):
        header = self.msg_byteorder.encode() + \
            PROTO_VERSION.to_bytes(1, self.byteorder) + \
            cmdtype.value.to_bytes(1, self.byteorder) + \
            size.to_bytes(2, self.byteorder)
        return header

    def encode_message(self, command):
        if not isinstance(command, PushCommand):
            raise PushException('Command must by GLib.Variant')
        data = command.variant.get_data_as_bytes()
        size = data.get_size()

        # Build the header
        header = self.encode_header(command.cmdtype, size)

        return header + data.get_data()

    def write(self, command):
        msg = self.encode_message(command)
        self.file.write(msg)
        self.file.flush()

    def send_info(self, repo):
        cmdtype = PushCommandType.info
        mode = repo.get_mode()
        _, refs = repo.list_refs(None, None)
        args = {
            'mode': GLib.Variant('i', mode),
            'refs': GLib.Variant('a{ss}', refs)
        }
        command = PushCommand(cmdtype, args)
        self.write(command)

    def send_update(self, refs):
        cmdtype = PushCommandType.update
        args = {}
        for branch, revs in refs.items():
            args[branch] = GLib.Variant('(ss)', revs)
        command = PushCommand(cmdtype, args)
        self.write(command)

    def send_putobjects(self, repo, objects):

        logging.info('Sending {} objects'.format(len(objects)))

        # Send command saying we're going to send a stream of objects
        cmdtype = PushCommandType.putobjects
        command = PushCommand(cmdtype, {})
        self.write(command)

        # Open a TarFile for writing uncompressed tar to a stream
        tar = tarfile.TarFile.open(mode='w|', fileobj=self.file)
        for obj in objects:

            logging.info('Sending object {}'.format(obj))
            objpath = ostree_object_path(repo, obj)
            stat = os.stat(objpath)

            tar_info = tarfile.TarInfo(obj)
            tar_info.mtime = stat.st_mtime
            tar_info.size = stat.st_size
            with open(objpath, 'rb') as obj_fp:
                tar.addfile(tar_info, obj_fp)

        # We're done, close the tarfile
        tar.close()

    def send_status(self, result, message=''):
        cmdtype = PushCommandType.status
        args = {
            'result': GLib.Variant('b', result),
            'message': GLib.Variant('s', message)
        }
        command = PushCommand(cmdtype, args)
        self.write(command)

    def send_done(self):
        command = PushCommand(PushCommandType.done, {})
        self.write(command)


class PushMessageReader(object):
    def __init__(self, file, byteorder=sys.byteorder, tmpdir=None):
        self.file = file
        self.byteorder = byteorder
        self.tmpdir = tmpdir

    def decode_header(self, header):
        if len(header) != HEADER_SIZE:
            raise Exception('Header is %d bytes, not %d' % (len(header), HEADER_SIZE))
        order = sys_byteorder(chr(header[0]))
        version = int(header[1])
        if version != PROTO_VERSION:
            raise Exception('Unsupported protocol version %d' % version)
        cmdtype = PushCommandType(int(header[2]))
        vlen = int.from_bytes(header[3:], order)
        return order, version, cmdtype, vlen

    def decode_message(self, message, size, order):
        if len(message) != size:
            raise Exception('Expected %d bytes, but got %d' % (size, len(message)))
        data = GLib.Bytes.new(message)
        variant = GLib.Variant.new_from_bytes(GLib.VariantType.new('a{sv}'),
                                              data, False)
        if order != self.byteorder:
            variant = GLib.Variant.byteswap(variant)

        return variant

    def read(self):
        header = self.file.read(HEADER_SIZE)
        if len(header) == 0:
            # Remote end quit
            return None, None
        order, version, cmdtype, size = self.decode_header(header)
        msg = self.file.read(size)
        if len(msg) != size:
            raise PushException('Did not receive full message')
        args = self.decode_message(msg, size, order)

        return cmdtype, args

    def receive(self, allowed):
        cmdtype, args = self.read()
        if cmdtype is None:
            raise PushException('Expected reply, got none')
        if cmdtype not in allowed:
            raise PushException('Unexpected reply type', cmdtype.name)
        return cmdtype, args.unpack()

    def receive_info(self):
        cmdtype, args = self.receive([PushCommandType.info])
        return args

    def receive_update(self):
        cmdtype, args = self.receive([PushCommandType.update])
        return args

    def receive_putobjects(self, repo):

        received_objects = []

        # Open a TarFile for reading uncompressed tar from a stream
        tar = tarfile.TarFile.open(mode='r|', fileobj=self.file)

        # Extract every tarinfo into the temp location
        #
        # This should block while tar.next() reads the next
        # tar object from the stream.
        while True:
            tar_info = tar.next()
            if not tar_info:
                break

            tar.extract(tar_info, self.tmpdir)
            received_objects.append(tar_info.name)

        # Finished with this stream
        tar.close()

        return received_objects

    def receive_status(self):
        cmdtype, args = self.receive([PushCommandType.status])
        return args

    def receive_done(self):
        cmdtype, args = self.receive([PushCommandType.done])
        return args


class OSTreePusher(object):
    def __init__(self, repopath, remotepath, branches=[], verbose=False,
                 debug=False, output=None):
        self.repopath = repopath
        self.remotepath = remotepath
        self.verbose = verbose
        self.debug = debug
        self.output = output

        self.remote_host = None
        self.remote_user = None
        self.remote_repo = None
        self.remote_port = None
        self._set_remote_args()

        if self.repopath is None:
            self.repo = OSTree.Repo.new_default()
        else:
            self.repo = OSTree.Repo.new(Gio.File.new_for_path(self.repopath))
        self.repo.open(None)

        # Enumerate branches to push
        if len(branches) == 0:
            _, self.refs = self.repo.list_refs(None, None)
        else:
            self.refs = {}
            for branch in branches:
                _, rev = self.repo.resolve_rev(branch, False)
                self.refs[branch] = rev

        # Start ssh
        ssh_cmd = ['ssh']
        if self.remote_user:
            ssh_cmd += ['-l', self.remote_user]
        if self.remote_port:
            ssh_cmd += ['-p', self.remote_port]
        ssh_cmd += [self.remote_host, 'bst-artifact-receive',
                    '--repo=%s' % self.remote_path]
        if self.verbose:
            ssh_cmd += ['--verbose']
        if self.debug:
            ssh_cmd += ['--debug']
        logging.info('Executing {}'.format(' '.join(ssh_cmd)))
        self.ssh = subprocess.Popen(ssh_cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=self.output,
                                    start_new_session=True)

        self.writer = PushMessageWriter(self.ssh.stdin)
        self.reader = PushMessageReader(self.ssh.stdout)

    def _set_remote_args(self):
        url = urlparse(self.remotepath)
        if url.netloc:
            if url.scheme != 'ssh':
                raise PushException('Only URL scheme ssh is allowed, '
                                    'not "%s"' % url.scheme)
            self.remote_host = url.hostname
            self.remote_user = url.username
            self.remote_repo = url.path
            self.remote_port = url.port
        else:
            # Scp/git style remote (user@hostname:path)
            self.remote_port = None
            parts = self.remotepath.split('@', 1)
            if len(parts) > 1:
                self.remote_user = parts[0]
                remainder = parts[1]
            else:
                self.remote_user = None
                remainder = parts[0]
            parts = remainder.split(':', 1)
            if len(parts) != 2:
                raise PushException('Remote repository "%s" does not '
                                    'contain a hostname and path separated '
                                    'by ":"' % self.remotepath)
            self.remote_host, self.remote_path = parts

    def needed_commits(self, remote, local, needed):
        parent = local
        if remote == '0' * 64:
            # Nonexistent remote branch, use None for convenience
            remote = None
        while parent != remote:
            needed.add(parent)
            _, commit = self.repo.load_variant_if_exists(OSTree.ObjectType.COMMIT,
                                                         parent)
            if commit is None:
                raise PushException('Shallow history from commit %s does '
                                    'not contain remote commit %s' % (local, remote))
            parent = OSTree.commit_get_parent(commit)
            if parent is None:
                break
        if remote is not None and parent != remote:
            raise PushExistsException('Remote commit %s not descendent of '
                                      'commit %s' % (remote, local))

    def needed_objects(self, commits):
        objects = set()
        for rev in commits:
            _, reachable = self.repo.traverse_commit(rev, 0, None)
            for obj in reachable:
                objname = OSTree.object_to_string(obj[0], obj[1])
                if obj[1] == OSTree.ObjectType.FILE:
                    # Make this a filez since we're archive-z2
                    objname += 'z'
                elif obj[1] == OSTree.ObjectType.COMMIT:
                    # Add in detached metadata
                    metaobj = objname + 'meta'
                    metapath = ostree_object_path(self.repo, metaobj)
                    if os.path.exists(metapath):
                        objects.add(metaobj)

                    # Add in Endless compat files
                    for suffix in ['sig', 'sizes2']:
                        metaobj = obj[0] + '.' + suffix
                        metapath = ostree_object_path(self.repo, metaobj)
                        if os.path.exists(metapath):
                            objects.add(metaobj)
                objects.add(objname)
        return objects

    def close(self):
        self.ssh.stdin.close()
        return self.ssh.wait()

    def run(self):
        remote_refs = {}
        update_refs = {}

        # Receive remote info
        logging.info('Receiving repository information')
        args = self.reader.receive_info()
        remote_mode = args['mode']
        if remote_mode != OSTree.RepoMode.ARCHIVE_Z2:
            raise PushException('Can only push to archive-z2 repos')
        remote_refs = args['refs']
        for branch, rev in self.refs.items():
            remote_rev = remote_refs.get(branch, '0' * 64)
            if rev != remote_rev:
                update_refs[branch] = remote_rev, rev
        if len(update_refs) == 0:
            logging.info('Nothing to update')
            self.writer.send_done()
            return self.close()

        # Send update command
        logging.info('Sending update request')
        self.writer.send_update(update_refs)

        # Receive status for update request
        args = self.reader.receive_status()
        if not args['result']:
            self.writer.send_done()
            raise PushException(args['message'])

        # Collect commits and objects to push
        commits = set()
        for branch, revs in update_refs.items():
            logging.info('Updating {} {} to {}'.format(branch, revs[0], revs[1]))
            needed = self.needed_commits(revs[0], revs[1], commits)
        logging.info('Enumerating objects to send')
        objects = self.needed_objects(commits)

        # Send all the objects to receiver, checking status after each
        self.writer.send_putobjects(self.repo, objects)

        return self.close()


class OSTreeReceiver(object):
    def __init__(self, repopath):
        self.repopath = repopath

        if self.repopath is None:
            self.repo = OSTree.Repo.new_default()
        else:
            self.repo = OSTree.Repo.new(Gio.File.new_for_path(self.repopath))
        self.repo.open(None)

        repo_tmp = os.path.join(self.repopath, 'tmp')
        self.tmpdir = tempfile.mkdtemp(dir=repo_tmp, prefix='bst-push-')
        self.writer = PushMessageWriter(sys.stdout.buffer)
        self.reader = PushMessageReader(sys.stdin.buffer, tmpdir=self.tmpdir)

        # Set a sane umask before writing any objects
        os.umask(0o0022)

    def close(self):
        shutil.rmtree(self.tmpdir)
        sys.stdout.close()
        return 0

    def run(self):
        try:
            exit_code = self.do_run()
            self.close()
            return exit_code
        except:
            # BLIND EXCEPT - Just abort if we receive any exception, this
            # can be a broken pipe, a tarfile read error when the remote
            # connection is closed, a bug; whatever happens we want to cleanup.
            self.close()
            raise

    def do_run(self):
        # Send info immediately
        self.writer.send_info(self.repo)

        # Wait for update or done command
        cmdtype, args = self.reader.receive([PushCommandType.update,
                                             PushCommandType.done])
        if cmdtype == PushCommandType.done:
            return 0
        update_refs = args
        for branch, revs in update_refs.items():
            # Check that each branch can be updated appropriately
            _, current = self.repo.resolve_rev(branch, True)
            if current is None:
                # From commit should be all 0s
                if revs[0] != '0' * 64:
                    self.writer.send_status(False,
                                            'Invalid from commit %s '
                                            'for new branch %s' % (revs[0], branch))
                    self.reader.receive_done()
                    return 1
            elif revs[0] != current:
                self.writer.send_status(False,
                                        'Branch %s is at %s, not %s' % (branch, current, revs[0]))
                self.reader.receive_done()
                return 1

        # All updates valid
        self.writer.send_status(True)

        # Wait for putobjects or done
        cmdtype, args = self.reader.receive([PushCommandType.putobjects,
                                             PushCommandType.done])

        if cmdtype == PushCommandType.done:
            logging.debug('Received done before any objects, exiting')
            return 0

        # Receive the actual objects
        received_objects = self.reader.receive_putobjects(self.repo)

        # If we didn't get any objects, we're done
        if len(received_objects) == 0:
            return 0

        # Got all objects, move them to the object store
        for obj in received_objects:
            tmp_path = os.path.join(self.tmpdir, obj)
            obj_path = ostree_object_path(self.repo, obj)
            os.makedirs(os.path.dirname(obj_path), exist_ok=True)
            logging.debug('Renaming {} to {}'.format(tmp_path, obj_path))
            os.rename(tmp_path, obj_path)

        # Finally, update the refs
        for branch, revs in update_refs.items():
            logging.debug('Setting ref {} to {}'.format(branch, revs[1]))
            self.repo.set_ref_immediate(None, branch, revs[1], None)

        return 0


# push()
#
# Run the pusher in process, with logging going to the output file
#
# Args:
#   repo: The local repository path
#   remote: The ssh remote url to push to
#   branch: The ref to push
#   output: The output where logging should go
def push(repo, remote, branch, output):

    logging.basicConfig(format='%(module)s: %(levelname)s: %(message)s',
                        level=logging.INFO, stream=output)

    pusher = OSTreePusher(repo, remote, [branch], True, False, output=output)

    def terminate_push():
        pusher.close()

    with _signals.terminator(terminate_push):
        try:
            return pusher.run()
        except PushException:
            terminate_push()
            raise
        except PushExistsException:
            # If the commit already existed, just bail out
            # on the push and dont bother re-raising the error
            logging.info("Ref {} was already present in remote {}".format(branch, remote))
            terminate_push()


def receive_main():
    aparser = ArgumentParser(description='Receive pushed ostree objects')
    aparser.add_argument('--repo', help='repository path')
    aparser.add_argument('-v', '--verbose', action='store_true',
                         help='enable verbose output')
    aparser.add_argument('--debug', action='store_true',
                         help='enable debugging output')
    args = aparser.parse_args()

    loglevel = logging.WARNING
    if args.verbose:
        loglevel = logging.INFO
    if args.debug:
        loglevel = logging.DEBUG
    logging.basicConfig(format='%(module)s: %(levelname)s: %(message)s',
                        level=loglevel, stream=sys.stderr)

    receiver = OSTreeReceiver(args.repo)
    return receiver.run()
