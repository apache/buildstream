#!/usr/bin/env python3
#
#  Copyright (C) 2018 Codethink Limited
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

import hashlib
import itertools
import multiprocessing
import os
import signal
import stat
import tempfile
from urllib.parse import urlparse

import grpc

from google.bytestream import bytestream_pb2, bytestream_pb2_grpc
from google.devtools.remoteexecution.v1test import remote_execution_pb2, remote_execution_pb2_grpc
from buildstream import buildstream_pb2, buildstream_pb2_grpc
from google.protobuf.message import DecodeError

from .. import _signals, utils
from .._exceptions import ArtifactError

from . import ArtifactCache


# A CASCache manages artifacts in a CAS repository as specified in the
# Remote Execution API.
#
# Args:
#     context (Context): The BuildStream context
#     enable_push (bool): Whether pushing is allowed by the platform
#
# Pushing is explicitly disabled by the platform in some cases,
# like when we are falling back to functioning without using
# user namespaces.
#
class CASCache(ArtifactCache):

    def __init__(self, context, *, enable_push=True):
        super().__init__(context)

        self.casdir = os.path.join(context.artifactdir, 'cas')
        os.makedirs(os.path.join(self.casdir, 'tmp'), exist_ok=True)

        self._enable_push = enable_push

        # Per-project list of _CASRemote instances.
        self._remotes = {}

        self._has_fetch_remotes = False
        self._has_push_remotes = False

    ################################################
    #     Implementation of abstract methods       #
    ################################################
    def contains(self, element, key):
        refpath = self._refpath(self.get_artifact_fullname(element, key))

        # This assumes that the repository doesn't have any dangling pointers
        return os.path.exists(refpath)

    def extract(self, element, key):
        ref = self.get_artifact_fullname(element, key)

        tree = self.resolve_ref(ref)

        dest = os.path.join(self.extractdir, element._get_project().name, element.normal_name, tree.hash)
        if os.path.isdir(dest):
            # artifact has already been extracted
            return dest

        os.makedirs(self.extractdir, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix='tmp', dir=self.extractdir) as tmpdir:
            checkoutdir = os.path.join(tmpdir, ref)
            self._checkout(checkoutdir, tree)

            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                os.rename(checkoutdir, dest)
            except OSError as e:
                # With rename it's possible to get either ENOTEMPTY or EEXIST
                # in the case that the destination path is a not empty directory.
                #
                # If rename fails with these errors, another process beat
                # us to it so just ignore.
                if e.errno not in [os.errno.ENOTEMPTY, os.errno.EEXIST]:
                    raise ArtifactError("Failed to extract artifact for ref '{}': {}"
                                        .format(ref, e)) from e

        return dest

    def commit(self, element, content, keys):
        refs = [self.get_artifact_fullname(element, key) for key in keys]

        tree = self._create_tree(content)

        for ref in refs:
            self.set_ref(ref, tree)

    def can_diff(self):
        return True

    def diff(self, element, key_a, key_b, *, subdir=None):
        ref_a = self.get_artifact_fullname(element, key_a)
        ref_b = self.get_artifact_fullname(element, key_b)

        tree_a = self.resolve_ref(ref_a)
        tree_b = self.resolve_ref(ref_b)

        if subdir:
            tree_a = self._get_subdir(tree_a, subdir)
            tree_b = self._get_subdir(tree_b, subdir)

        added = []
        removed = []
        modified = []

        self._diff_trees(tree_a, tree_b, added=added, removed=removed, modified=modified)

        return modified, removed, added

    def initialize_remotes(self, *, on_failure=None):
        remote_specs = self.global_remote_specs

        for project in self.project_remote_specs:
            remote_specs += self.project_remote_specs[project]

        remote_specs = list(utils._deduplicate(remote_specs))

        remotes = {}
        q = multiprocessing.Queue()
        for remote_spec in remote_specs:
            # Use subprocess to avoid creation of gRPC threads in main BuildStream process
            p = multiprocessing.Process(target=self._initialize_remote, args=(remote_spec, q))

            try:
                # Keep SIGINT blocked in the child process
                with _signals.blocked([signal.SIGINT], ignore=False):
                    p.start()

                error = q.get()
                p.join()
            except KeyboardInterrupt:
                utils._kill_process_tree(p.pid)
                raise

            if error and on_failure:
                on_failure(remote_spec.url, error)
            elif error:
                raise ArtifactError(error)
            else:
                self._has_fetch_remotes = True
                if remote_spec.push:
                    self._has_push_remotes = True

                remotes[remote_spec.url] = _CASRemote(remote_spec)

        for project in self.context.get_projects():
            remote_specs = self.global_remote_specs
            if project in self.project_remote_specs:
                remote_specs = list(utils._deduplicate(remote_specs + self.project_remote_specs[project]))

            project_remotes = []

            for remote_spec in remote_specs:
                # Errors are already handled in the loop above,
                # skip unreachable remotes here.
                if remote_spec.url not in remotes:
                    continue

                remote = remotes[remote_spec.url]
                project_remotes.append(remote)

            self._remotes[project] = project_remotes

    def has_fetch_remotes(self, *, element=None):
        if not self._has_fetch_remotes:
            # No project has fetch remotes
            return False
        elif element is None:
            # At least one (sub)project has fetch remotes
            return True
        else:
            # Check whether the specified element's project has fetch remotes
            remotes_for_project = self._remotes[element._get_project()]
            return bool(remotes_for_project)

    def has_push_remotes(self, *, element=None):
        if not self._has_push_remotes or not self._enable_push:
            # No project has push remotes
            return False
        elif element is None:
            # At least one (sub)project has push remotes
            return True
        else:
            # Check whether the specified element's project has push remotes
            remotes_for_project = self._remotes[element._get_project()]
            return any(remote.spec.push for remote in remotes_for_project)

    def pull(self, element, key, *, progress=None):
        ref = self.get_artifact_fullname(element, key)

        project = element._get_project()

        for remote in self._remotes[project]:
            try:
                remote.init()

                request = buildstream_pb2.GetArtifactRequest()
                request.key = ref
                response = remote.artifact_cache.GetArtifact(request)

                tree = remote_execution_pb2.Digest()
                tree.hash = response.artifact.hash
                tree.size_bytes = response.artifact.size_bytes

                self._fetch_directory(remote, tree)

                self.set_ref(ref, tree)

                # no need to pull from additional remotes
                return True

            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.NOT_FOUND:
                    raise

        return False

    def link_key(self, element, oldkey, newkey):
        oldref = self.get_artifact_fullname(element, oldkey)
        newref = self.get_artifact_fullname(element, newkey)

        tree = self.resolve_ref(oldref)

        self.set_ref(newref, tree)

    def push_key_only(self, key, project):

        ref = key

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        pushed = False

        for remote in push_remotes:
            remote.init()

            if self._push_refs_to_remote([ref], remote):
                pushed = True

        return pushed

    def verify_key_pushed(self, key, project):
        ref = key

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        pushed = False

        for remote in push_remotes:
            remote.init()

            if self._verify_ref_on_remote(ref, remote):
                pushed = True

        return pushed

    def _push_refs_to_remote(self, refs, remote):
        pushed = False
        for ref in refs:
            tree = self.resolve_ref(ref)

            # Check whether ref is already on the server in which case
            # there is no need to push the artifact
            try:
                request = buildstream_pb2.GetArtifactRequest()
                request.key = ref
                response = remote.artifact_cache.GetArtifact(request)

                if response.artifact.hash == tree.hash and response.artifact.size_bytes == tree.size_bytes:
                    # ref is already on the server with the same tree
                    continue

            except grpc.RpcError as e:
                if e.code() != grpc.StatusCode.NOT_FOUND:
                    raise

            missing_blobs = {}
            required_blobs = self._required_blobs(tree)

            # Limit size of FindMissingBlobs request
            for required_blobs_group in _grouper(required_blobs, 512):
                request = remote_execution_pb2.FindMissingBlobsRequest()

                for required_digest in required_blobs_group:
                    d = request.blob_digests.add()
                    d.hash = required_digest.hash
                    d.size_bytes = required_digest.size_bytes

                response = remote.cas.FindMissingBlobs(request)
                for digest in response.missing_blob_digests:
                    d = remote_execution_pb2.Digest()
                    d.hash = digest.hash
                    d.size_bytes = digest.size_bytes
                    missing_blobs[d.hash] = d

            # Upload any blobs missing on the server
            for digest in missing_blobs.values():
                def request_stream():
                    resource_name = os.path.join(digest.hash, str(digest.size_bytes))
                    with open(self.objpath(digest), 'rb') as f:
                        assert os.fstat(f.fileno()).st_size == digest.size_bytes
                        offset = 0
                        finished = False
                        remaining = digest.size_bytes
                        while not finished:
                            chunk_size = min(remaining, 64 * 1024)
                            remaining -= chunk_size

                            request = bytestream_pb2.WriteRequest()
                            request.write_offset = offset
                            # max. 64 kB chunks
                            request.data = f.read(chunk_size)
                            request.resource_name = resource_name
                            request.finish_write = remaining <= 0
                            yield request
                            offset += chunk_size
                            finished = request.finish_write
                response = remote.bytestream.Write(request_stream())

            request = buildstream_pb2.UpdateArtifactRequest()
            request.keys.append(ref)
            request.artifact.hash = tree.hash
            request.artifact.size_bytes = tree.size_bytes
            remote.artifact_cache.UpdateArtifact(request)

            pushed = True
        return pushed

    def _verify_ref_on_remote(self, ref, remote):
        pushed = False
        tree = self.resolve_ref(ref)

        # Check whether ref is already on the server in which case
        # there is no need to push the artifact
        try:
            request = buildstream_pb2.GetArtifactRequest()
            request.key = ref
            response = remote.artifact_cache.GetArtifact(request)

            if response.artifact.hash == tree.hash and response.artifact.size_bytes == tree.size_bytes:
                # ref is already on the server with the same tree
                return True

        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.NOT_FOUND:
                raise

        return False

    def push(self, element, keys):
        keys = list(keys)
        refs = [self.get_artifact_fullname(element, key) for key in keys]
        element.info("Pushing keys ({}): {}".format(len(keys),",".join(["'{}'".format(k) for k in keys])))
        element.info("Pushing refs ({}): {}".format(len(refs),",".join(refs)))
        project = element._get_project()

        push_remotes = [r for r in self._remotes[project] if r.spec.push]

        pushed = False

        for remote in push_remotes:
            remote.init()

            if self._push_refs_to_remote(refs, remote):
                pushed = True

        return pushed

    ################################################
    #                API Private Methods           #
    ################################################

    # objpath():
    #
    # Return the path of an object based on its digest.
    #
    # Args:
    #     digest (Digest): The digest of the object
    #
    # Returns:
    #     (str): The path of the object
    #
    def objpath(self, digest):
        return os.path.join(self.casdir, 'objects', digest.hash[:2], digest.hash[2:])

    # add_object():
    #
    # Hash and write object to CAS.
    #
    # Args:
    #     digest (Digest): An optional Digest object to populate
    #     path (str): Path to file to add
    #     buffer (bytes): Byte buffer to add
    #
    # Returns:
    #     (Digest): The digest of the added object
    #
    # Either `path` or `buffer` must be passed, but not both.
    #
    def add_object(self, *, digest=None, path=None, buffer=None):
        # Exactly one of the two parameters has to be specified
        assert (path is None) != (buffer is None)

        if digest is None:
            digest = remote_execution_pb2.Digest()

        try:
            h = hashlib.sha256()
            # Always write out new file to avoid corruption if input file is modified
            with tempfile.NamedTemporaryFile(dir=os.path.join(self.casdir, 'tmp')) as out:
                if path:
                    with open(path, 'rb') as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            h.update(chunk)
                            out.write(chunk)
                else:
                    h.update(buffer)
                    out.write(buffer)

                out.flush()

                digest.hash = h.hexdigest()
                digest.size_bytes = os.fstat(out.fileno()).st_size

                # Place file at final location
                objpath = self.objpath(digest)
                os.makedirs(os.path.dirname(objpath), exist_ok=True)
                os.link(out.name, objpath)

        except FileExistsError as e:
            # We can ignore the failed link() if the object is already in the repo.
            pass

        except OSError as e:
            raise ArtifactError("Failed to hash object: {}".format(e)) from e

        return digest

    # set_ref():
    #
    # Create or replace a ref.
    #
    # Args:
    #     ref (str): The name of the ref
    #
    def set_ref(self, ref, tree):
        refpath = self._refpath(ref)
        os.makedirs(os.path.dirname(refpath), exist_ok=True)
        with utils.save_file_atomic(refpath, 'wb') as f:
            f.write(tree.SerializeToString())

    # resolve_ref():
    #
    # Resolve a ref to a digest.
    #
    # Args:
    #     ref (str): The name of the ref
    #
    # Returns:
    #     (Digest): The digest stored in the ref
    #
    def resolve_ref(self, ref):
        refpath = self._refpath(ref)

        try:
            with open(refpath, 'rb') as f:
                digest = remote_execution_pb2.Digest()
                digest.ParseFromString(f.read())
                return digest

        except FileNotFoundError as e:
            raise ArtifactError("Attempt to access unavailable artifact: {}".format(e)) from e

    ################################################
    #             Local Private Methods            #
    ################################################
    def _checkout(self, dest, tree):
        os.makedirs(dest, exist_ok=True)

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), 'rb') as f:
            directory.ParseFromString(f.read())

        for filenode in directory.files:
            # regular file, create hardlink
            fullpath = os.path.join(dest, filenode.name)
            os.link(self.objpath(filenode.digest), fullpath)

            if filenode.is_executable:
                os.chmod(fullpath, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP |
                         stat.S_IROTH | stat.S_IXOTH)

        for dirnode in directory.directories:
            fullpath = os.path.join(dest, dirnode.name)
            self._checkout(fullpath, dirnode.digest)

        for symlinknode in directory.symlinks:
            # symlink
            fullpath = os.path.join(dest, symlinknode.name)
            os.symlink(symlinknode.target, fullpath)

    def _refpath(self, ref):
        return os.path.join(self.casdir, 'refs', 'heads', ref)

    def _create_tree(self, path, *, digest=None):
        directory = remote_execution_pb2.Directory()

        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            mode = os.lstat(full_path).st_mode
            if stat.S_ISDIR(mode):
                dirnode = directory.directories.add()
                dirnode.name = name
                self._create_tree(full_path, digest=dirnode.digest)
            elif stat.S_ISREG(mode):
                filenode = directory.files.add()
                filenode.name = name
                self.add_object(path=full_path, digest=filenode.digest)
                filenode.is_executable = (mode & stat.S_IXUSR) == stat.S_IXUSR
            elif stat.S_ISLNK(mode):
                symlinknode = directory.symlinks.add()
                symlinknode.name = name
                symlinknode.target = os.readlink(full_path)
            else:
                raise ArtifactError("Unsupported file type for {}".format(full_path))

        return self.add_object(digest=digest, buffer=directory.SerializeToString())

    def _get_subdir(self, tree, subdir):
        head, name = os.path.split(subdir)
        if head:
            tree = self._get_subdir(tree, head)

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), 'rb') as f:
            directory.ParseFromString(f.read())

        for dirnode in directory.directories:
            if dirnode.name == name:
                return dirnode.digest

        raise ArtifactError("Subdirectory {} not found".format(name))

    def _diff_trees(self, tree_a, tree_b, *, added, removed, modified, path=""):
        dir_a = remote_execution_pb2.Directory()
        dir_b = remote_execution_pb2.Directory()

        if tree_a:
            with open(self.objpath(tree_a), 'rb') as f:
                dir_a.ParseFromString(f.read())
        if tree_b:
            with open(self.objpath(tree_b), 'rb') as f:
                dir_b.ParseFromString(f.read())

        a = 0
        b = 0
        while a < len(dir_a.files) or b < len(dir_b.files):
            if b < len(dir_b.files) and (a >= len(dir_a.files) or
                                         dir_a.files[a].name > dir_b.files[b].name):
                added.append(os.path.join(path, dir_b.files[b].name))
                b += 1
            elif a < len(dir_a.files) and (b >= len(dir_b.files) or
                                           dir_b.files[b].name > dir_a.files[a].name):
                removed.append(os.path.join(path, dir_a.files[a].name))
                a += 1
            else:
                # File exists in both directories
                if dir_a.files[a].digest.hash != dir_b.files[b].digest.hash:
                    modified.append(os.path.join(path, dir_a.files[a].name))
                a += 1
                b += 1

        a = 0
        b = 0
        while a < len(dir_a.directories) or b < len(dir_b.directories):
            if b < len(dir_b.directories) and (a >= len(dir_a.directories) or
                                               dir_a.directories[a].name > dir_b.directories[b].name):
                self._diff_trees(None, dir_b.directories[b].digest,
                                 added=added, removed=removed, modified=modified,
                                 path=os.path.join(path, dir_b.directories[b].name))
                b += 1
            elif a < len(dir_a.directories) and (b >= len(dir_b.directories) or
                                                 dir_b.directories[b].name > dir_a.directories[a].name):
                self._diff_trees(dir_a.directories[a].digest, None,
                                 added=added, removed=removed, modified=modified,
                                 path=os.path.join(path, dir_a.directories[a].name))
                a += 1
            else:
                # Subdirectory exists in both directories
                if dir_a.directories[a].digest.hash != dir_b.directories[b].digest.hash:
                    self._diff_trees(dir_a.directories[a].digest, dir_b.directories[b].digest,
                                     added=added, removed=removed, modified=modified,
                                     path=os.path.join(path, dir_a.directories[a].name))
                a += 1
                b += 1

    def _initialize_remote(self, remote_spec, q):
        try:
            remote = _CASRemote(remote_spec)
            remote.init()

            request = buildstream_pb2.StatusRequest()
            response = remote.artifact_cache.Status(request)

            if remote_spec.push and not response.allow_updates:
                q.put('Artifact server does not allow push')
            else:
                # No error
                q.put(None)

        except Exception as e:               # pylint: disable=broad-except
            # Whatever happens, we need to return it to the calling process
            #
            q.put(str(e))

    def _required_blobs(self, tree):
        # parse directory, and recursively add blobs
        d = remote_execution_pb2.Digest()
        d.hash = tree.hash
        d.size_bytes = tree.size_bytes
        yield d

        directory = remote_execution_pb2.Directory()

        with open(self.objpath(tree), 'rb') as f:
            try:
                directory.ParseFromString(f.read())
            except DecodeError as d:
                # OK, that probably wasn't a directory. In which case, it has no dependencies.
                return

        for filenode in directory.files:
            d = remote_execution_pb2.Digest()
            d.hash = filenode.digest.hash
            d.size_bytes = filenode.digest.size_bytes
            yield d

        for dirnode in directory.directories:
            yield from self._required_blobs(dirnode.digest)

    def _fetch_blob(self, remote, digest, out):
        resource_name = os.path.join(digest.hash, str(digest.size_bytes))
        request = bytestream_pb2.ReadRequest()
        request.resource_name = resource_name
        request.read_offset = 0
        for response in remote.bytestream.Read(request):
            out.write(response.data)

        out.flush()
        assert digest.size_bytes == os.fstat(out.fileno()).st_size

    def _fetch_directory(self, remote, tree):
        objpath = self.objpath(tree)
        if os.path.exists(objpath):
            # already in local cache
            return

        with tempfile.NamedTemporaryFile(dir=os.path.join(self.casdir, 'tmp')) as out:
            self._fetch_blob(remote, tree, out)

            directory = remote_execution_pb2.Directory()

            with open(out.name, 'rb') as f:
                directory.ParseFromString(f.read())

            for filenode in directory.files:
                fileobjpath = self.objpath(tree)
                if os.path.exists(fileobjpath):
                    # already in local cache
                    continue

                with tempfile.NamedTemporaryFile(dir=os.path.join(self.casdir, 'tmp')) as f:
                    self._fetch_blob(remote, filenode.digest, f)

                    digest = self.add_object(path=f.name)
                    assert digest.hash == filenode.digest.hash

            for dirnode in directory.directories:
                self._fetch_directory(remote, dirnode.digest)

            # place directory blob only in final location when we've downloaded
            # all referenced blobs to avoid dangling references in the repository
            digest = self.add_object(path=out.name)
            assert digest.hash == tree.hash


# Represents a single remote CAS cache.
#
class _CASRemote():
    def __init__(self, spec):
        self.spec = spec
        self._initialized = False
        self.channel = None
        self.bytestream = None
        self.cas = None
        self.artifact_cache = None

    def init(self):
        if not self._initialized:
            url = urlparse(self.spec.url)
            if url.scheme == 'http':
                port = url.port or 80
                self.channel = grpc.insecure_channel('{}:{}'.format(url.hostname, port))
            elif url.scheme == 'https':
                port = url.port or 443

                if self.spec.server_cert:
                    with open(self.spec.server_cert, 'rb') as f:
                        server_cert_bytes = f.read()
                else:
                    server_cert_bytes = None

                if self.spec.client_key:
                    with open(self.spec.client_key, 'rb') as f:
                        client_key_bytes = f.read()
                else:
                    client_key_bytes = None

                if self.spec.client_cert:
                    with open(self.spec.client_cert, 'rb') as f:
                        client_cert_bytes = f.read()
                else:
                    client_cert_bytes = None

                credentials = grpc.ssl_channel_credentials(root_certificates=server_cert_bytes,
                                                           private_key=client_key_bytes,
                                                           certificate_chain=client_cert_bytes)
                self.channel = grpc.secure_channel('{}:{}'.format(url.hostname, port), credentials)
            else:
                raise ArtifactError("Unsupported URL: {}".format(self.spec.url))

            self.bytestream = bytestream_pb2_grpc.ByteStreamStub(self.channel)
            self.cas = remote_execution_pb2_grpc.ContentAddressableStorageStub(self.channel)
            self.artifact_cache = buildstream_pb2_grpc.ArtifactCacheStub(self.channel)

            self._initialized = True


def _grouper(iterable, n):
    # pylint: disable=stop-iteration-return
    while True:
        yield itertools.chain([next(iterable)], itertools.islice(iterable, n - 1))
