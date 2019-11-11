#
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors: Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#
import os
from urllib.parse import urlparse

import grpc
import pytest

from buildstream._protos.buildstream.v2.artifact_pb2 import Artifact, GetArtifactRequest, UpdateArtifactRequest
from buildstream._protos.buildstream.v2.artifact_pb2_grpc import ArtifactServiceStub
from buildstream._protos.build.bazel.remote.execution.v2 import remote_execution_pb2 as re_pb2
from buildstream import utils

from tests.testutils.artifactshare import create_artifact_share


def test_artifact_get_not_found(tmpdir):
    sharedir = os.path.join(str(tmpdir), "share")
    with create_artifact_share(sharedir) as share:
        # set up artifact service stub
        url = urlparse(share.repo)
        with grpc.insecure_channel("{}:{}".format(url.hostname, url.port)) as channel:
            artifact_stub = ArtifactServiceStub(channel)

            # Run GetArtifact and check it throws a not found error
            request = GetArtifactRequest()
            request.cache_key = "@artifact/something/not_there"
            try:
                artifact_stub.GetArtifact(request)
            except grpc.RpcError as e:
                assert e.code() == grpc.StatusCode.NOT_FOUND
                assert e.details() == "Artifact proto not found"
            else:
                assert False


# Successfully getting the artifact
@pytest.mark.parametrize("files", ["present", "absent", "invalid"])
def test_update_artifact(tmpdir, files):
    sharedir = os.path.join(str(tmpdir), "share")
    with create_artifact_share(sharedir, casd=True) as share:
        # put files object
        if files == "present":
            directory = re_pb2.Directory()
            digest = share.cas.add_object(buffer=directory.SerializeToString())
        elif files == "invalid":
            digest = share.cas.add_object(buffer="abcdefghijklmnop".encode("utf-8"))
        elif files == "absent":
            digest = utils._message_digest("abcdefghijklmnop".encode("utf-8"))

        url = urlparse(share.repo)

        with grpc.insecure_channel("{}:{}".format(url.hostname, url.port)) as channel:
            artifact_stub = ArtifactServiceStub(channel)

            # initialise an artifact
            artifact = Artifact()
            artifact.version = 0
            artifact.build_success = True
            artifact.strong_key = "abcdefghijklmnop"
            artifact.files.hash = "hashymchashash"
            artifact.files.size_bytes = 10

            artifact.files.CopyFrom(digest)

            # Put it in the artifact share with an UpdateArtifactRequest
            request = UpdateArtifactRequest()
            request.artifact.CopyFrom(artifact)
            request.cache_key = "a-cache-key"

            # should return the same artifact back
            if files == "present":
                response = artifact_stub.UpdateArtifact(request)
                assert response == artifact
            else:
                try:
                    artifact_stub.UpdateArtifact(request)
                except grpc.RpcError as e:
                    assert e.code() == grpc.StatusCode.FAILED_PRECONDITION
                    if files == "absent":
                        assert e.details() == "Artifact files specified but no files found"
                    elif files == "invalid":
                        assert e.details() == "Artifact files specified but directory not found"
                    return

            # If we uploaded the artifact check GetArtifact
            request = GetArtifactRequest()
            request.cache_key = "a-cache-key"

            response = artifact_stub.GetArtifact(request)
            assert response == artifact
