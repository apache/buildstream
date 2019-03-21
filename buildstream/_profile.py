#
#  Copyright (C) 2017 Codethink Limited
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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        James Ennis <james.ennis@codethink.co.uk>
#        Benjamin Schubert <bschubert15@bloomberg.net>


import contextlib
import cProfile
import pstats
import os
import datetime
import time


# Use the topic values here to decide what to profile
# by setting them in the BST_PROFILE environment variable.
#
# Multiple topics can be set with the ':' separator.
#
# E.g.:
#
#   BST_PROFILE=circ-dep-check:sort-deps bst <command> <args>
#
# The special 'all' value will enable all profiles.
class Topics():
    CIRCULAR_CHECK = 'circ-dep-check'
    SORT_DEPENDENCIES = 'sort-deps'
    LOAD_CONTEXT = 'load-context'
    LOAD_PROJECT = 'load-project'
    LOAD_PIPELINE = 'load-pipeline'
    LOAD_SELECTION = 'load-selection'
    SCHEDULER = 'scheduler'
    ALL = 'all'


class _Profile:
    def __init__(self, key, message):
        self.profiler = cProfile.Profile()

        self.key = key
        self.message = message

        self.start_time = time.time()
        filename_template = os.path.join(
            os.getcwd(),
            "profile-{}-{}".format(
                datetime.datetime.fromtimestamp(self.start_time).strftime("%Y%m%dT%H%M%S"),
                self.key.replace("/", "-").replace(".", "-")
            )
        )
        self.log_filename = "{}.log".format(filename_template)
        self.cprofile_filename = "{}.cprofile".format(filename_template)

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
        self.save()

    def start(self):
        self.profiler.enable()

    def stop(self):
        self.profiler.disable()

    def save(self):
        self._save_log()
        self.profiler.dump_stats(self.cprofile_filename)

    def _save_log(self):
        heading = "\n".join([
            "-" * 64,
            "Profile for key: {}".format(self.key),
            "Started at: {}".format(self.start_time),
            "\n\t{}".format(self.message) if self.message else "",
            "-" * 64,
            ""  # for a final new line
        ])

        with open(self.log_filename, "a") as fp:
            fp.write(heading)
            ps = pstats.Stats(self.profiler, stream=fp).sort_stats("cumulative")
            ps.print_stats()


class _Profiler:
    def __init__(self, settings):
        self.active_topics = set()
        self.enabled_topics = set()

        if settings:
            self.enabled_topics = {
                topic
                for topic in settings.split(":")
            }

    @contextlib.contextmanager
    def profile(self, topic, key, message=None):
        if not self._is_profile_enabled(topic):
            yield
            return

        key = "{}-{}".format(topic, key)

        assert key not in self.active_topics
        self.active_topics.add(key)

        profiler = _Profile(key, message)

        with profiler:
            yield

        self.active_topics.remove(key)

    def _is_profile_enabled(self, topic):
        return topic in self.enabled_topics or Topics.ALL in self.enabled_topics


# Export a profiler to be used by BuildStream
PROFILER = _Profiler(os.getenv("BST_PROFILE"))
