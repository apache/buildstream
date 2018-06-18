#
#  Copyright (C) 2017 Codethink Limited
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

import cProfile
import pstats
import os
import datetime
import time

# Track what profile topics are active
active_topics = {}
active_profiles = {}
initialized = False


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
    LOAD_LOADER = 'load-loader'
    LOAD_CONTEXT = 'load-context'
    LOAD_PROJECT = 'load-project'
    LOAD_PIPELINE = 'load-pipeline'
    SHOW = 'show'
    ARTIFACT_RECEIVE = 'artifact-receive'
    ALL = 'all'


class Profile():
    def __init__(self, topic, key, message):
        self.message = message
        self.key = topic + '-' + key
        self.start = time.time()
        self.profiler = cProfile.Profile()
        self.profiler.enable()

    def end(self):
        self.profiler.disable()

        filename = self.key.replace('/', '-')
        filename = filename.replace('.', '-')
        filename = os.path.join(os.getcwd(), 'profile-' + filename + '.log')

        with open(filename, "a", encoding="utf-8") as f:

            dt = datetime.datetime.fromtimestamp(self.start)
            time_ = dt.strftime('%Y-%m-%d %H:%M:%S')

            heading = '================================================================\n'
            heading += 'Profile for key: {}\n'.format(self.key)
            heading += 'Started at: {}\n'.format(time_)
            if self.message:
                heading += '\n    {}'.format(self.message)
            heading += '================================================================\n'
            f.write(heading)
            ps = pstats.Stats(self.profiler, stream=f).sort_stats('cumulative')
            ps.print_stats()


# profile_start()
#
# Start profiling for a given topic.
#
# Args:
#    topic (str): A topic name
#    key (str): A key for this profile run
#    message (str): An optional message to print in profile results
#
def profile_start(topic, key, message=None):
    if not profile_enabled(topic):
        return

    # Start profiling and hold on to the key
    profile = Profile(topic, key, message)
    assert active_profiles.get(profile.key) is None
    active_profiles[profile.key] = profile


# profile_end()
#
# Ends a profiling session previously
# started with profile_start()
#
# Args:
#    topic (str): A topic name
#    key (str): A key for this profile run
#
def profile_end(topic, key):
    if not profile_enabled(topic):
        return

    topic_key = topic + '-' + key
    profile = active_profiles.get(topic_key)
    assert profile
    profile.end()
    del active_profiles[topic_key]


def profile_init():
    global initialized  # pylint: disable=global-statement
    if not initialized:
        setting = os.getenv('BST_PROFILE')
        if setting:
            topics = setting.split(':')
            for topic in topics:
                active_topics[topic] = True
        initialized = True


def profile_enabled(topic):
    profile_init()
    if active_topics.get(topic):
        return True
    if active_topics.get(Topics.ALL):
        return True
    return False
