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
from ._exceptions import ProfileError


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
class Topics:
    CIRCULAR_CHECK = "circ-dep-check"
    SORT_DEPENDENCIES = "sort-deps"
    LOAD_CONTEXT = "load-context"
    LOAD_PROJECT = "load-project"
    LOAD_PIPELINE = "load-pipeline"
    LOAD_SELECTION = "load-selection"
    SCHEDULER = "scheduler"
    ALL = "all"


class _Profile:
    def __init__(self, key, message):
        self.profiler = cProfile.Profile()
        self._additional_pstats_files = []

        self.key = key
        self.message = message

        self.start_time = time.time()
        filename_template = os.path.join(
            os.getcwd(),
            "profile-{}-{}".format(
                datetime.datetime.fromtimestamp(self.start_time).strftime("%Y%m%dT%H%M%S"),
                self.key.replace("/", "-").replace(".", "-"),
            ),
        )
        self.log_filename = "{}.log".format(filename_template)
        self.cprofile_filename = "{}.cprofile".format(filename_template)

    def __enter__(self):
        self.start()

    def __exit__(self, _exc_type, _exc_value, traceback):
        self.stop()
        self.save()

    def merge(self, profile):
        self._additional_pstats_files.append(profile.cprofile_filename)

    def start(self):
        self.profiler.enable()

    def stop(self):
        self.profiler.disable()

    def save(self):
        heading = "\n".join(
            [
                "-" * 64,
                "Profile for key: {}".format(self.key),
                "Started at: {}".format(self.start_time),
                "\n\t{}".format(self.message) if self.message else "",
                "-" * 64,
                "",  # for a final new line
            ]
        )

        with open(self.log_filename, "a") as fp:
            stats = pstats.Stats(self.profiler, *self._additional_pstats_files, stream=fp)

            # Create the log file
            fp.write(heading)
            stats.sort_stats("cumulative")
            stats.print_stats()

            # Dump the cprofile
            stats.dump_stats(self.cprofile_filename)


class _Profiler:
    def __init__(self, settings):
        self.active_topics = set()
        self.enabled_topics = set()
        self._active_profilers = []
        self._valid_topics = False

        if settings:
            self.enabled_topics = set(settings.split(":"))

    @contextlib.contextmanager
    def profile(self, topic, key, message=None):

        # Check if the user enabled topics are valid
        # NOTE: This is done in the first PROFILER.profile() call and
        # not __init__ to ensure we handle the exception. This also means
        # we cannot test for the exception due to the early instantiation and
        # how the environment is set in the test invocation.
        if not self._valid_topics:
            self._check_valid_topics()

        if not self._is_profile_enabled(topic):
            yield
            return

        if self._active_profilers:
            # we are in a nested profiler, stop the parent
            self._active_profilers[-1].stop()

        key = "{}-{}".format(topic, key)

        assert key not in self.active_topics
        self.active_topics.add(key)

        profiler = _Profile(key, message)
        self._active_profilers.append(profiler)

        with profiler:
            yield

        self.active_topics.remove(key)

        # Remove the last profiler from the list
        self._active_profilers.pop()

        if self._active_profilers:
            # We were in a previous profiler, add the previous results to it
            # and reenable it.
            parent_profiler = self._active_profilers[-1]
            parent_profiler.merge(profiler)
            parent_profiler.start()

    def _is_profile_enabled(self, topic):
        return topic in self.enabled_topics or Topics.ALL in self.enabled_topics

    def _check_valid_topics(self):
        non_valid_topics = [topic for topic in self.enabled_topics if topic not in vars(Topics).values()]

        if non_valid_topics:
            raise ProfileError("Provided BST_PROFILE topics do not exist: {}".format(", ".join(non_valid_topics)))

        self._valid_topics = True


# Export a profiler to be used by BuildStream
PROFILER = _Profiler(os.getenv("BST_PROFILE"))
