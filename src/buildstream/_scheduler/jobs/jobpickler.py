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
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Angelos Evripiotis <jevripiotis@bloomberg.net>


import copyreg
import io
import pickle

from ..._protos.buildstream.v2.artifact_pb2 import Artifact as ArtifactProto
from ..._protos.build.bazel.remote.execution.v2.remote_execution_pb2 import Digest as DigestProto

# BuildStream toplevel imports
from ..._loader import Loader
from ..._messenger import Messenger
from ... import utils, node

# Note that `str(type(proto_class))` results in `GeneratedProtocolMessageType`
# instead of the concrete type, so we come up with our own names here.
_NAME_TO_PROTO_CLASS = {
    "artifact": ArtifactProto,
    "digest": DigestProto,
}

_PROTO_CLASS_TO_NAME = {cls: name for name, cls in _NAME_TO_PROTO_CLASS.items()}


# pickle_child_job()
#
# Perform the special case pickling required to pickle a child job for
# unpickling in a child process.
#
# Args:
#    child_job     (ChildJob): The job to pickle.
#    projects (List[Project]): The list of loaded projects, so we can get the
#                              relevant factories.
#
def pickle_child_job(child_job, projects):
    # Note that we need to consider all the state of the program that's
    # necessary for the job, this includes e.g. the global state of the node
    # module.
    node_module_state = node._get_state_for_pickling()
    return _pickle_child_job_data((child_job, node_module_state), projects,)


# do_pickled_child_job()
#
# Unpickle the supplied 'pickled' job and call 'child_action' on it.
#
# This is expected to be run in a subprocess started from the main process, as
# such it will fixup any globals to be in the expected state.
#
# Args:
#    pickled     (BytesIO): The pickled data, and job to execute.
#    *child_args (any)    : Any parameters to be passed to `child_action`.
#
def do_pickled_child_job(pickled, *child_args):
    utils._is_main_process = _not_main_process

    child_job, node_module_state = pickle.load(pickled)
    node._set_state_from_pickling(node_module_state)
    return child_job.child_action(*child_args)


# _not_main_process()
#
# A function to replace `utils._is_main_process` when we're running in a
# subprocess that was not forked - the inheritance of the main process id will
# not work in this case.
#
# Note that we'll always not be the main process by definition.
#
def _not_main_process():
    return False


# _pickle_child_job_data()
#
# Perform the special case pickling required to pickle a child job for
# unpickling in a child process.
#
# Note that this just enables the pickling of things that contain ChildJob-s,
# the thing to be pickled doesn't have to be a ChildJob.
#
# Note that we don't need an `unpickle_child_job_data`, as regular
# `pickle.load()` will do everything required.
#
# Args:
#    child_job_data (ChildJob): The job to be pickled.
#    projects  (List[Project]): The list of loaded projects, so we can get the
#                               relevant factories.
#
# Returns:
#    An `io.BytesIO`, with the pickled contents of the ChildJob and everything it
#    transitively refers to.
#
# Some types require special handling when pickling to send to another process.
# We register overrides for those special cases:
#
# o Very stateful objects: Some things carry much more state than they need for
#   pickling over to the child job process. This extra state brings
#   complication of supporting pickling of more types, and the performance
#   penalty of the actual pickling. Use private knowledge of these objects to
#   safely reduce the pickled state.
#
# o gRPC objects: These don't pickle, but they do have their own serialization
#   mechanism, which we use instead. To avoid modifying generated code, we
#   instead register overrides here.
#
# o Plugins: These cannot be unpickled unless the factory which created them
#   has been unpickled first, with the same identifier as before. See note
#   below. Some state in plugins is not necessary for child jobs, and comes
#   with a heavy cost; we also need to remove this before pickling.
#
def _pickle_child_job_data(child_job_data, projects):

    factory_list = [
        factory
        for p in projects
        for factory in [
            p.config.element_factory,
            p.first_pass_config.element_factory,
            p.config.source_factory,
            p.first_pass_config.source_factory,
        ]
    ]

    plugin_class_to_factory = {
        cls: factory for factory in factory_list if factory is not None for cls, _ in factory.all_loaded_plugins()
    }

    pickled_data = io.BytesIO()
    pickler = pickle.Pickler(pickled_data)
    pickler.dispatch_table = copyreg.dispatch_table.copy()

    def reduce_plugin(plugin):
        return _reduce_plugin_with_factory_dict(plugin, plugin_class_to_factory)

    for cls in plugin_class_to_factory:
        pickler.dispatch_table[cls] = reduce_plugin
    pickler.dispatch_table[ArtifactProto] = _reduce_proto
    pickler.dispatch_table[DigestProto] = _reduce_proto
    pickler.dispatch_table[Loader] = _reduce_object
    pickler.dispatch_table[Messenger] = _reduce_object

    pickler.dump(child_job_data)
    pickled_data.seek(0)

    return pickled_data


def _reduce_object(instance):
    cls = type(instance)
    state = instance.get_state_for_child_job_pickling()
    return (cls.__new__, (cls,), state)


def _reduce_proto(instance):
    name = _PROTO_CLASS_TO_NAME[type(instance)]
    data = instance.SerializeToString()
    return (_new_proto_from_reduction_args, (name, data))


def _new_proto_from_reduction_args(name, data):
    cls = _NAME_TO_PROTO_CLASS[name]
    instance = cls()
    instance.ParseFromString(data)
    return instance


def _reduce_plugin_with_factory_dict(plugin, plugin_class_to_factory):
    meta_kind, state = plugin._get_args_for_child_job_pickling()
    assert meta_kind
    factory = plugin_class_to_factory[type(plugin)]
    args = (factory, meta_kind)
    return (_new_plugin_from_reduction_args, args, state)


def _new_plugin_from_reduction_args(factory, meta_kind):
    cls, _ = factory.lookup(meta_kind)
    plugin = cls.__new__(cls)

    # Note that we rely on the `__project` member of the Plugin to keep
    # `factory` alive after the scope of this function. If `factory` were to be
    # GC'd then we would see undefined behaviour.

    return plugin
