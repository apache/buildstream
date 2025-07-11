#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

from .._protos.build.buildgrid import local_cas_pb2

from .._cas import CASRemote


class RERemote(CASRemote):
    def __init__(self, cas_spec, remote_execution_specs, cascache):
        super().__init__(cas_spec, cascache)

        self.remote_execution_specs = remote_execution_specs
        self.exec_service = None
        self.operations_service = None
        self.ac_service = None

    def _configure_protocols(self):
        local_cas = self.cascache.get_local_cas()
        request = local_cas_pb2.GetInstanceNameForRemotesRequest()
        if self.remote_execution_specs.storage_spec:
            self.remote_execution_specs.storage_spec.to_localcas_remote(request.content_addressable_storage)
        else:
            self.spec.to_localcas_remote(request.content_addressable_storage)
        if self.remote_execution_specs.exec_spec:
            self.remote_execution_specs.exec_spec.to_localcas_remote(request.execution)
        if self.remote_execution_specs.action_spec:
            self.remote_execution_specs.action_spec.to_localcas_remote(request.action_cache)
        response = local_cas.GetInstanceNameForRemotes(request)
        self.local_cas_instance_name = response.instance_name

        casd = self.cascache.get_casd()
        self.exec_service = casd.get_exec_service()
        self.operations_service = casd.get_operations_service()
        self.ac_service = casd.get_ac_service()
