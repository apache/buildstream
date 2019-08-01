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

import multiprocessing


# QueueManager()
#
# This abstracts our choice of creating picklable or non-picklable Queues.
#
# Note that when choosing the 'spawn' or 'forkserver' methods of starting
# processes with the `multiprocessing` standard library module, we must use
# only picklable type as parameters to jobs.
#
class QueueManager:
    def make_queue_wrapper(self):
        return _PlainQueueWrapper(multiprocessing.Queue())


# QueueWrapper()
#
# This abstracts our choice of using picklable or non-picklable Queues.
#
class QueueWrapper:
    pass


class _PlainQueueWrapper(QueueWrapper):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def set_potential_callback_on_queue_event(self, event_loop, callback):
        # Warning: Platform specific code up ahead
        #
        #   The multiprocessing.Queue object does not tell us how
        #   to receive io events in the receiving process, so we
        #   need to sneak in and get its file descriptor.
        #
        #   The _reader member of the Queue is currently private
        #   but well known, perhaps it will become public:
        #
        #      http://bugs.python.org/issue3831
        #
        event_loop.add_reader(self.queue._reader.fileno(), callback)

    def clear_potential_callback_on_queue_event(self, event_loop):
        event_loop.remove_reader(self.queue._reader.fileno())

    def close(self):
        self.queue.close()
