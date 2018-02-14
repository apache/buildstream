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

import click
import logging
import os
import subprocess
import sys
import shutil
import tarfile
import tempfile
import multiprocessing
from enum import Enum
from urllib.parse import urlparse

from .. import _signals

import gi
gi.require_version('OSTree', '1.0')
from gi.repository import GLib, Gio, OSTree  # nopep8


PROTO_VERSION = 1
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
        raise PushException('Unrecognized system byteorder {}'
                            .format(sys_byteorder))


def sys_byteorder(msg_byteorder):
    if msg_byteorder == 'l':
        return 'little'
    elif msg_byteorder == 'B':
        return 'big'
    else:
        raise PushException('Unrecognized message byteorder {}'
                            .format(msg_byteorder))


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

    def send_hello(self):
        # The 'hello' message is used to check connectivity and discover the
        # cache's pull URL. It's actually transmitted as an empty info request.
        args = {
            'mode': GLib.Variant('i', 0),
            'refs': GLib.Variant('a{ss}', {})
        }
        command = PushCommand(PushCommandType.info, args)
        self.write(command)

    def send_info(self, repo, refs, pull_url=None):
        cmdtype = PushCommandType.info
        mode = repo.get_mode()

        ref_map = {}
        for ref in refs:
            _, checksum = repo.resolve_rev(ref, True)
            if checksum:
                _, has_object = repo.has_object(OSTree.ObjectType.COMMIT, ref, None)
                if has_object:
                    ref_map[ref] = checksum

        args = {
            'mode': GLib.Variant('i', mode),
            'refs': GLib.Variant('a{ss}', ref_map)
        }

        # The server sends this so clients can discover the correct pull URL
        # for this cache without requiring end-users to specify it.
        if pull_url:
            args['pull_url'] = GLib.Variant('s', pull_url)

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
            raise Exception('Header is {:d} bytes, not {:d}'.format(len(header), HEADER_SIZE))
        order = sys_byteorder(chr(header[0]))
        version = int(header[1])
        if version != PROTO_VERSION:
            raise Exception('Unsupported protocol version {:d}'.format(version))
        cmdtype = PushCommandType(int(header[2]))
        vlen = int.from_bytes(header[3:], order)
        return order, version, cmdtype, vlen

    def decode_message(self, message, size, order):
        if len(message) != size:
            raise Exception('Expected {:d} bytes, but got {:d}'.format(size, len(message)))
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
            filepos = tar.fileobj.tell()
            tar_info = tar.next()
            if not tar_info:
                # End of stream marker consists of two 512 Byte blocks.
                # Current Python tarfile stops reading after the first block.
                # Read the second block as well to ensure the stream is at
                # the right position for following messages.
                if tar.fileobj.tell() - filepos < 1024:
                    tar.fileobj.read(512)
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


def parse_remote_location(remotepath):
    """Parse remote artifact cache URL that's been specified in our config."""
    remote_host = remote_user = remote_repo = None

    url = urlparse(remotepath, scheme='file')
    if url.scheme:
        if url.scheme not in ['file', 'ssh']:
            raise PushException('Only URL schemes file and ssh are allowed, '
                                'not "{}"'.format(url.scheme))
        remote_host = url.hostname
        remote_user = url.username
        remote_repo = url.path
        remote_port = url.port or 22
    else:
        # Scp/git style remote (user@hostname:path)
        parts = remotepath.split('@', 1)
        if len(parts) > 1:
            remote_user = parts[0]
            remainder = parts[1]
        else:
            remote_user = None
            remainder = parts[0]
        parts = remainder.split(':', 1)
        if len(parts) != 2:
            raise PushException('Remote repository "{}" does not '
                                'contain a hostname and path separated '
                                'by ":"'.format(remotepath))
        remote_host, remote_repo = parts
        # This form doesn't make it possible to specify a non-standard port.
        remote_port = 22

    return remote_host, remote_user, remote_repo, remote_port


def ssh_commandline(remote_host, remote_user=None, remote_port=22):
    if remote_host is None:
        return []

    ssh_cmd = ['ssh']
    if remote_user:
        ssh_cmd += ['-l', remote_user]
    if remote_port != 22:
        ssh_cmd += ['-p', str(remote_port)]
    ssh_cmd += [remote_host]
    return ssh_cmd


def foo_run(func, args, stdin_fd, stdout_fd, stderr_fd):
    sys.stdin = open(stdin_fd, 'r')
    sys.stdout = open(stdout_fd, 'w')
    sys.stderr = open(stderr_fd, 'w')
    func(args)


class ProcessWithPipes(object):
    def __init__(self, func, args, *, stderr=None):
        r0, w0 = os.pipe()
        r1, w1 = os.pipe()
        if stderr is None:
            r2, w2 = os.pipe()
        else:
            w2 = stderr.fileno()
        self.proc = multiprocessing.Process(target=foo_run, args=(func, args, r0, w1, w2))
        self.proc.start()
        self.stdin = open(w0, 'wb')
        os.close(r0)
        self.stdout = open(r1, 'rb')
        os.close(w1)
        if stderr is None:
            self.stderr = open(r2, 'rb')
            os.close(w2)

    def wait(self):
        self.proc.join()
        self.returncode = self.proc.exitcode


class OSTreePusher(object):
    def __init__(self, repopath, remotepath, branches=None, verbose=False,
                 debug=False, output=None):
        self.repopath = repopath
        self.remotepath = remotepath
        self.verbose = verbose
        self.debug = debug
        self.output = output

        self.remote_host, self.remote_user, self.remote_repo, self.remote_port = \
            parse_remote_location(remotepath)

        if self.repopath is None:
            self.repo = OSTree.Repo.new_default()
        else:
            self.repo = OSTree.Repo.new(Gio.File.new_for_path(self.repopath))
        self.repo.open(None)

        # Enumerate branches to push
        if branches is None:
            _, self.refs = self.repo.list_refs(None, None)
        else:
            self.refs = {}
            for branch in branches:
                _, rev = self.repo.resolve_rev(branch, False)
                self.refs[branch] = rev

        # Start ssh
        ssh_cmd = ssh_commandline(self.remote_host, self.remote_user, self.remote_port)

        ssh_cmd += ['bst-artifact-receive']
        if self.verbose:
            ssh_cmd += ['--verbose']
        if self.debug:
            ssh_cmd += ['--debug']
        if not self.remote_host:
            ssh_cmd += ['--pull-url', self.remote_repo]
        ssh_cmd += [self.remote_repo]

        logging.info('Executing {}'.format(' '.join(ssh_cmd)))

        if self.remote_host:
            self.ssh = subprocess.Popen(ssh_cmd, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=self.output,
                                        start_new_session=True)
        else:
            self.ssh = ProcessWithPipes(receive_main, ssh_cmd[1:], stderr=self.output)

        self.writer = PushMessageWriter(self.ssh.stdin)
        self.reader = PushMessageReader(self.ssh.stdout)

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
                raise PushException('Shallow history from commit {} does '
                                    'not contain remote commit {}'.format(local, remote))
            parent = OSTree.commit_get_parent(commit)
            if parent is None:
                break
        if remote is not None and parent != remote:
            self.writer.send_done()
            raise PushExistsException('Remote commit {} not descendent of '
                                      'commit {}'.format(remote, local))

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

        # Send info immediately
        self.writer.send_info(self.repo, list(self.refs.keys()))

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
        exc_info = None
        ref_count = 0
        for branch, revs in update_refs.items():
            logging.info('Updating {} {} to {}'.format(branch, revs[0], revs[1]))
            try:
                self.needed_commits(revs[0], revs[1], commits)
                ref_count += 1
            except PushExistsException:
                if exc_info is None:
                    exc_info = sys.exc_info()

        # Re-raise PushExistsException if all refs exist already
        if ref_count == 0 and exc_info:
            raise exc_info[0].with_traceback(exc_info[1], exc_info[2])

        logging.info('Enumerating objects to send')
        objects = self.needed_objects(commits)

        # Send all the objects to receiver, checking status after each
        self.writer.send_putobjects(self.repo, objects)

        # Inform receiver that all objects have been sent
        self.writer.send_done()

        # Wait until receiver has completed
        self.reader.receive_done()

        return self.close()


# OSTreeReceiver is on the receiving end of an OSTree push.
#
# Args:
#     repopath (str): On-disk location of the receiving repository.
#     pull_url (str): Redirection for clients who want to pull, not push.
#
class OSTreeReceiver(object):
    def __init__(self, repopath, pull_url):
        self.repopath = repopath
        self.pull_url = pull_url

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
        sys.stdout.flush()
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
        # Receive remote info
        args = self.reader.receive_info()
        remote_refs = args['refs']

        # Send info back
        self.writer.send_info(self.repo, list(remote_refs.keys()),
                              pull_url=self.pull_url)

        # Wait for update or done command
        cmdtype, args = self.reader.receive([PushCommandType.update,
                                             PushCommandType.done])
        if cmdtype == PushCommandType.done:
            return 0
        update_refs = args

        self.writer.send_status(True)

        # Wait for putobjects or done
        cmdtype, args = self.reader.receive([PushCommandType.putobjects,
                                             PushCommandType.done])

        if cmdtype == PushCommandType.done:
            logging.debug('Received done before any objects, exiting')
            return 0

        # Receive the actual objects
        received_objects = self.reader.receive_putobjects(self.repo)

        # Ensure that pusher has sent all objects
        self.reader.receive_done()

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

        # Verify that we have the specified commit objects
        for branch, revs in update_refs.items():
            _, has_object = self.repo.has_object(OSTree.ObjectType.COMMIT, revs[1], None)
            if not has_object:
                raise PushException('Missing commit {} for ref {}'.format(revs[1], branch))

        # Finally, update the refs
        for branch, revs in update_refs.items():
            logging.debug('Setting ref {} to {}'.format(branch, revs[1]))
            self.repo.set_ref_immediate(None, branch, revs[1], None)

        # Inform pusher that everything is in place
        self.writer.send_done()

        return 0


# initialize_push_connection()
#
# Test that we can connect to the remote bst-artifact-receive program, and
# receive the pull URL for this artifact cache.
#
# We don't want to make the user wait until the first artifact has been built
# to discover that they actually cannot push, so this should be called early.
#
# The SSH push protocol doesn't allow pulling artifacts. We don't want to
# require users to specify two URLs for a single cache, so we have the push
# protocol return the corresponding pull URL as part of the 'hello' response.
#
# Args:
#   remote: The ssh remote url to push to
#
# Returns:
#   (str): The URL that should be used for pushing to this cache.
#
# Raises:
#   PushException if there was an issue connecting to the remote.
def initialize_push_connection(remote):
    remote_host, remote_user, remote_repo, remote_port = parse_remote_location(remote)
    ssh_cmd = ssh_commandline(remote_host, remote_user, remote_port)

    if remote_host:
        # We need a short timeout here because if 'remote' isn't reachable at
        # all, the process will hang until the connection times out.
        ssh_cmd += ['-oConnectTimeout=3']

    ssh_cmd += ['bst-artifact-receive', remote_repo]

    if remote_host:
        ssh = subprocess.Popen(ssh_cmd, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        ssh_cmd += ['--pull-url', remote_repo]
        ssh = ProcessWithPipes(receive_main, ssh_cmd[1:])

    writer = PushMessageWriter(ssh.stdin)
    reader = PushMessageReader(ssh.stdout)

    try:
        writer.send_hello()
        args = reader.receive_info()
        writer.send_done()

        if 'pull_url' in args:
            pull_url = args['pull_url']
        else:
            raise PushException(
                "Remote cache did not tell us its pull URL. This cache probably "
                "requires updating to a newer version of `bst-artifact-receive`.")
    except PushException as protocol_error:
        # If we get a read error on the wire, let's first see if SSH reported
        # an error such as 'Permission denied'. If so this will be much more
        # useful to the user than the "Expected reply, got none" sort of
        # message that reader.receive_info() will have raised.
        ssh.wait()
        if ssh.returncode != 0:
            ssh_error = ssh.stderr.read().decode('unicode-escape').strip()
            raise PushException("{}".format(ssh_error))
        else:
            raise protocol_error

    return pull_url


# push()
#
# Run the pusher in process, with logging going to the output file
#
# Args:
#   repo: The local repository path
#   remote: The ssh remote url to push to
#   branches: The refs to push
#   output: The output where logging should go
#
# Returns:
#   (bool): True if the remote was updated, False if it already existed
#           and no updated was required
#
# Raises:
#   PushException if there was an error
#
def push(repo, remote, branches, output):

    logging.basicConfig(format='%(module)s: %(levelname)s: %(message)s',
                        level=logging.INFO, stream=output)

    pusher = OSTreePusher(repo, remote, branches, True, False, output=output)

    def terminate_push():
        pusher.close()

    with _signals.terminator(terminate_push):
        try:
            pusher.run()
            return True
        except ConnectionError as e:
            # Connection attempt failed or connection was terminated unexpectedly
            terminate_push()
            raise PushException("Connection failed") from e
        except PushException:
            terminate_push()
            raise
        except PushExistsException:
            # If the commit already existed, just bail out
            # on the push and dont bother re-raising the error
            logging.info("Ref {} was already present in remote {}".format(branches, remote))
            terminate_push()
            return False


@click.command(short_help="Receive pushed artifacts over ssh")
@click.option('--verbose', '-v', is_flag=True, default=False, help="Verbose mode")
@click.option('--debug', '-d', is_flag=True, default=False, help="Debug mode")
@click.option('--pull-url', type=str, required=True,
              help="Clients who try to pull over SSH will be redirected here")
@click.argument('repo')
def receive_main(verbose, debug, pull_url, repo):
    """A BuildStream sister program for receiving artifacts send to a shared artifact cache
    """
    loglevel = logging.WARNING
    if verbose:
        loglevel = logging.INFO
    if debug:
        loglevel = logging.DEBUG
    logging.basicConfig(format='%(module)s: %(levelname)s: %(message)s',
                        level=loglevel, stream=sys.stderr)

    receiver = OSTreeReceiver(repo, pull_url)
    return receiver.run()
