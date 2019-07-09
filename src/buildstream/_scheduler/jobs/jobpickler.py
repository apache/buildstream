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

# BuildStream toplevel imports
from ... import Element, Source
from ..._loader import Loader
from ..._messenger import Messenger


def _reduce_artifact_proto(instance):
    assert isinstance(instance, ArtifactProto)
    data = instance.SerializeToString()
    return (_unreduce_artifact_proto, (data,))


def _unreduce_artifact_proto(data):
    instance = ArtifactProto()
    instance.ParseFromString(data)
    return instance


def _reduce_loader(instance):
    assert isinstance(instance, Loader)
    state = instance.__dict__.copy()

    # When pickling a Loader over to the ChildJob, we don't want to bring
    # the whole Stream over with it. The _fetch_subprojects member is a method
    # of the Stream. We also don't want to remove it in the main process. If we
    # remove it in the child process then we will already be too late. The only
    # time that seems just right is here, when preparing the child process'
    # copy of the Loader.
    #
    del state['_fetch_subprojects']

    return (Loader.__new__, (Loader,), state)


def _reduce_messenger(instance):
    assert isinstance(instance, Messenger)
    state = instance.__dict__.copy()

    # When pickling a Messenger over to the ChildJob, we don't want to bring
    # the whole _message_handler over with it. We also don't want to remove it
    # in the main process. If we remove it in the child process then we will
    # already be too late. The only time that seems just right is here, when
    # preparing the child process' copy of the Messenger.
    #
    # Another approach might be to use a context manager on the Messenger,
    # which removes and restores the _message_handler. This wouldn't require
    # access to private details of Messenger.
    #
    del state['_message_handler']

    return (Messenger.__new__, (Messenger,), state)


def _reduce_element(element):
    assert isinstance(element, Element)
    meta_kind = element._meta_kind
    project = element._get_project()
    factory = project.config.element_factory
    args = (factory, meta_kind)
    state = element.__dict__.copy()
    state["_Element__reverse_dependencies"] = None
    state["_Element__buildable_callback"] = None
    return (_unreduce_plugin, args, state)


def _reduce_source(source):
    assert isinstance(source, Source)
    meta_kind = source._meta_kind
    project = source._get_project()
    factory = project.config.source_factory
    args = (factory, meta_kind)
    return (_unreduce_plugin, args, source.__dict__.copy())


def _unreduce_plugin(factory, meta_kind):
    cls, _ = factory.lookup(meta_kind)
    plugin = cls.__new__(cls)

    # TODO: find a better way of persisting this factory, otherwise the plugin
    # will become invalid.
    plugin.factory = factory

    return plugin


def pickle_child_job(child_job, context):

    # Note: Another way of doing this would be to let PluginBase do it's
    # import-magic. We would achieve this by first pickling the factories, and
    # the string names of their plugins. Unpickling the plugins in the child
    # process would then "just work". There would be an additional cost of
    # having to load every plugin kind, regardless of which ones are used.

    projects = context.get_projects()
    element_classes = [
        cls
        for p in projects
        for cls, _ in p.config.element_factory._types.values()
    ]
    source_classes = [
        cls
        for p in projects
        for cls, _ in p.config.source_factory._types.values()
    ]

    data = io.BytesIO()
    pickler = pickle.Pickler(data)
    pickler.dispatch_table = copyreg.dispatch_table.copy()
    for cls in element_classes:
        pickler.dispatch_table[cls] = _reduce_element
    for cls in source_classes:
        pickler.dispatch_table[cls] = _reduce_source
    pickler.dispatch_table[ArtifactProto] = _reduce_artifact_proto
    pickler.dispatch_table[Loader] = _reduce_loader
    pickler.dispatch_table[Messenger] = _reduce_messenger

    # import buildstream.testpickle
    # test_pickler = buildstream.testpickle.TestPickler()
    # test_pickler.dispatch_table = pickler.dispatch_table.copy()
    # test_pickler.test_dump(child_job)

    pickler.dump(child_job)
    data.seek(0)

    path = f"{child_job.action_name}_{child_job._task_id}"
    with open(path, "wb") as f:
        f.write(data.getvalue())

    return data


def unpickle_child_job(pickled):
    child_job = pickle.load(pickled)
    return child_job
