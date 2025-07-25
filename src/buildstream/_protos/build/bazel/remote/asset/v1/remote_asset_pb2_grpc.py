# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

from buildstream._protos.build.bazel.remote.asset.v1 import remote_asset_pb2 as build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2

GRPC_GENERATED_VERSION = '1.69.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in build/bazel/remote/asset/v1/remote_asset_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class FetchStub(object):
    """The Fetch service resolves or fetches assets referenced by URI and
    Qualifiers, returning a Digest for the content in 
    [ContentAddressableStorage][build.bazel.remote.execution.v2.ContentAddressableStorage].

    As with other services in the Remote Execution API, any call may return an
    error with a [RetryInfo][google.rpc.RetryInfo] error detail providing
    information about when the client should retry the request; clients SHOULD
    respect the information provided.
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.FetchBlob = channel.unary_unary(
                '/build.bazel.remote.asset.v1.Fetch/FetchBlob',
                request_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchBlobRequest.SerializeToString,
                response_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchBlobResponse.FromString,
                _registered_method=True)
        self.FetchDirectory = channel.unary_unary(
                '/build.bazel.remote.asset.v1.Fetch/FetchDirectory',
                request_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchDirectoryRequest.SerializeToString,
                response_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchDirectoryResponse.FromString,
                _registered_method=True)


class FetchServicer(object):
    """The Fetch service resolves or fetches assets referenced by URI and
    Qualifiers, returning a Digest for the content in 
    [ContentAddressableStorage][build.bazel.remote.execution.v2.ContentAddressableStorage].

    As with other services in the Remote Execution API, any call may return an
    error with a [RetryInfo][google.rpc.RetryInfo] error detail providing
    information about when the client should retry the request; clients SHOULD
    respect the information provided.
    """

    def FetchBlob(self, request, context):
        """Resolve or fetch referenced assets, making them available to the caller and
        other consumers in the [ContentAddressableStorage][build.bazel.remote.execution.v2.ContentAddressableStorage].

        Servers *MAY* fetch content that they do not already have cached, for any
        URLs they support.

        Servers *SHOULD* ensure that referenced files are present in the CAS at the
        time of the response, and (if supported) that they will remain available
        for a reasonable period of time. The lifetimes of the referenced blobs *SHOULD*
        be increased if necessary and applicable.
        In the event that a client receives a reference to content that is no
        longer present, it *MAY* re-issue the request with
        `oldest_content_accepted` set to a more recent timestamp than the original
        attempt, to induce a re-fetch from origin.

        Servers *MAY* cache fetched content and reuse it for subsequent requests,
        subject to `oldest_content_accepted`.

        Servers *MAY* support the complementary [Push][build.bazel.remote.asset.v1.Push]
        API and allow content to be directly inserted for use in future fetch
        responses.

        Servers *MUST* ensure Fetch'd content matches all the specified
        qualifiers except in the case of previously Push'd resources, for which
        the server *MAY* trust the pushing client to have set the qualifiers
        correctly, without validation.

        Servers not implementing the complementary [Push][build.bazel.remote.asset.v1.Push]
        API *MUST* reject requests containing qualifiers it does not support.

        Servers *MAY* transform assets as part of the fetch. For example a
        tarball fetched by [FetchDirectory][build.bazel.remote.asset.v1.Fetch.FetchDirectory]
        might be unpacked, or a Git repository
        fetched by [FetchBlob][build.bazel.remote.asset.v1.Fetch.FetchBlob]
        might be passed through `git-archive`.

        Errors handling the requested assets will be returned as gRPC Status errors
        here; errors outside the server's control will be returned inline in the
        `status` field of the response (see comment there for details).
        The possible RPC errors include:
        * `INVALID_ARGUMENT`: One or more arguments were invalid, such as a
        qualifier that is not supported by the server.
        * `RESOURCE_EXHAUSTED`: There is insufficient quota of some resource to
        perform the requested operation. The client may retry after a delay.
        * `UNAVAILABLE`: Due to a transient condition the operation could not be
        completed. The client should retry.
        * `INTERNAL`: An internal error occurred while performing the operation.
        The client should retry.
        * `DEADLINE_EXCEEDED`: The fetch could not be completed within the given
        RPC deadline. The client should retry for at least as long as the value
        provided in `timeout` field of the request.

        In the case of unsupported qualifiers, the server *SHOULD* additionally
        send a [BadRequest][google.rpc.BadRequest] error detail where, for each
        unsupported qualifier, there is a `FieldViolation` with a `field` of
        `qualifiers.name` and a `description` of `"{qualifier}" not supported`
        indicating the name of the unsupported qualifier.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def FetchDirectory(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_FetchServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'FetchBlob': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchBlob,
                    request_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchBlobRequest.FromString,
                    response_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchBlobResponse.SerializeToString,
            ),
            'FetchDirectory': grpc.unary_unary_rpc_method_handler(
                    servicer.FetchDirectory,
                    request_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchDirectoryRequest.FromString,
                    response_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchDirectoryResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'build.bazel.remote.asset.v1.Fetch', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('build.bazel.remote.asset.v1.Fetch', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class Fetch(object):
    """The Fetch service resolves or fetches assets referenced by URI and
    Qualifiers, returning a Digest for the content in 
    [ContentAddressableStorage][build.bazel.remote.execution.v2.ContentAddressableStorage].

    As with other services in the Remote Execution API, any call may return an
    error with a [RetryInfo][google.rpc.RetryInfo] error detail providing
    information about when the client should retry the request; clients SHOULD
    respect the information provided.
    """

    @staticmethod
    def FetchBlob(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/build.bazel.remote.asset.v1.Fetch/FetchBlob',
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchBlobRequest.SerializeToString,
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchBlobResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def FetchDirectory(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/build.bazel.remote.asset.v1.Fetch/FetchDirectory',
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchDirectoryRequest.SerializeToString,
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.FetchDirectoryResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)


class PushStub(object):
    """The Push service is complementary to the Fetch, and allows for
    associating contents of URLs to be returned in future Fetch API calls.

    As with other services in the Remote Execution API, any call may return an
    error with a [RetryInfo][google.rpc.RetryInfo] error detail providing
    information about when the client should retry the request; clients SHOULD
    respect the information provided.
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.PushBlob = channel.unary_unary(
                '/build.bazel.remote.asset.v1.Push/PushBlob',
                request_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushBlobRequest.SerializeToString,
                response_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushBlobResponse.FromString,
                _registered_method=True)
        self.PushDirectory = channel.unary_unary(
                '/build.bazel.remote.asset.v1.Push/PushDirectory',
                request_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushDirectoryRequest.SerializeToString,
                response_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushDirectoryResponse.FromString,
                _registered_method=True)


class PushServicer(object):
    """The Push service is complementary to the Fetch, and allows for
    associating contents of URLs to be returned in future Fetch API calls.

    As with other services in the Remote Execution API, any call may return an
    error with a [RetryInfo][google.rpc.RetryInfo] error detail providing
    information about when the client should retry the request; clients SHOULD
    respect the information provided.
    """

    def PushBlob(self, request, context):
        """These APIs associate the identifying information of a resource, as
        indicated by URI and optionally Qualifiers, with content available in the
        CAS. For example, associating a repository url and a commit id with a
        Directory Digest.

        Servers *SHOULD* only allow trusted clients to associate content, and *MAY*
        only allow certain URIs to be pushed.

        Clients *MUST* ensure associated content is available in CAS prior to
        pushing.

        Clients *MUST* ensure the Qualifiers listed correctly match the contents,
        and Servers *MAY* trust these values without validation.
        Fetch servers *MAY* require exact match of all qualifiers when returning
        content previously pushed, or allow fetching content with only a subset of
        the qualifiers specified on Push.

        Clients can specify expiration information that the server *SHOULD*
        respect. Subsequent requests can be used to alter the expiration time.

        A minimal compliant Fetch implementation may support only Push'd content
        and return `NOT_FOUND` for any resource that was not pushed first.
        Alternatively, a compliant implementation may choose to not support Push
        and only return resources that can be Fetch'd from origin.

        Errors will be returned as gRPC Status errors.
        The possible RPC errors include:
        * `INVALID_ARGUMENT`: One or more arguments to the RPC were invalid.
        * `RESOURCE_EXHAUSTED`: There is insufficient quota of some resource to
        perform the requested operation. The client may retry after a delay.
        * `UNAVAILABLE`: Due to a transient condition the operation could not be
        completed. The client should retry.
        * `INTERNAL`: An internal error occurred while performing the operation.
        The client should retry.
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def PushDirectory(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_PushServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'PushBlob': grpc.unary_unary_rpc_method_handler(
                    servicer.PushBlob,
                    request_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushBlobRequest.FromString,
                    response_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushBlobResponse.SerializeToString,
            ),
            'PushDirectory': grpc.unary_unary_rpc_method_handler(
                    servicer.PushDirectory,
                    request_deserializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushDirectoryRequest.FromString,
                    response_serializer=build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushDirectoryResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'build.bazel.remote.asset.v1.Push', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('build.bazel.remote.asset.v1.Push', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class Push(object):
    """The Push service is complementary to the Fetch, and allows for
    associating contents of URLs to be returned in future Fetch API calls.

    As with other services in the Remote Execution API, any call may return an
    error with a [RetryInfo][google.rpc.RetryInfo] error detail providing
    information about when the client should retry the request; clients SHOULD
    respect the information provided.
    """

    @staticmethod
    def PushBlob(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/build.bazel.remote.asset.v1.Push/PushBlob',
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushBlobRequest.SerializeToString,
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushBlobResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def PushDirectory(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/build.bazel.remote.asset.v1.Push/PushDirectory',
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushDirectoryRequest.SerializeToString,
            build_dot_bazel_dot_remote_dot_asset_dot_v1_dot_remote__asset__pb2.PushDirectoryResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
