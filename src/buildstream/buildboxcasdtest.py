import os
import pathlib
import shutil
import subprocess
import tempfile
import time

import click
import grpc

# from ._protos.google.rpc import code_pb2
from ._protos.build.bazel.remote.execution.v2 import remote_execution_pb2, remote_execution_pb2_grpc
from ._protos.build.buildgrid import local_cas_pb2, local_cas_pb2_grpc
# from ._protos.buildstream.v2 import buildstream_pb2

from . import utils


@click.command(name='bst-buildboxcasd-test', short_help="Test buildboxcasd")
@click.option('--no-server', is_flag=True, default=False, help="Don't start a casd server.")
def cli(no_server):
    path = os.path.abspath('./castemp')
    os.makedirs(path, exist_ok=True)

    # Place socket in global/user temporary directory to avoid hitting
    # the socket path length limit.
    # casd_socket_tempdir = tempfile.mkdtemp(prefix='buildstream')
    # casd_socket_path = os.path.join(casd_socket_tempdir, 'casd.sock')
    # casd_conn_str = f'unix:{casd_socket_path}'
    casd_conn_str = f'localhost:9000'

    if not no_server:
        casd_args = [utils.get_host_tool('buildbox-casd')]
        casd_args.append('--bind=' + casd_conn_str)
        casd_args.append('--verbose')

        casd_args.append(path)
        casd_process = subprocess.Popen(casd_args, cwd=path)
    casd_start_time = time.time()

    # time.sleep(3)
    local_cas = _get_local_cas(casd_start_time, casd_conn_str)
    # print(local_cas)

    path_to_add = pathlib.Path('file_to_add')
    path_to_add.write_text("Hello!")

    for _ in range(20):
        request = local_cas_pb2.CaptureFilesRequest()
        request.path.append(os.path.abspath(str(path_to_add)))
        response = local_cas.CaptureFiles(request)
        print('.', end='', flush=True)
    # print(response)

    time.sleep(3)

    if not no_server:
        casd_process.terminate()
        try:
            # Don't print anything if buildbox-casd terminates quickly
            casd_process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                casd_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                casd_process.kill()
                casd_process.wait(timeout=15)
        casd_process = None

    # shutil.rmtree(casd_socket_tempdir)


def _get_local_cas(casd_start_time, casd_conn_str):
    casd_channel = grpc.insecure_channel(casd_conn_str)
    local_cas = local_cas_pb2_grpc.LocalContentAddressableStorageStub(casd_channel)

    # Call GetCapabilities() to establish connection to casd
    capabilities = remote_execution_pb2_grpc.CapabilitiesStub(casd_channel)
    while True:
        try:
            capabilities.GetCapabilities(remote_execution_pb2.GetCapabilitiesRequest())
            break
        except grpc.RpcError as e:
            print(e)
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                if time.time() < casd_start_time + 2:
                    time.sleep(0.5)
                    continue

            raise

    return local_cas
