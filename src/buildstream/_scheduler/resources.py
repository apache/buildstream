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


class ResourceType:
    CACHE = 0
    DOWNLOAD = 1
    PROCESS = 2
    UPLOAD = 3


class Resources:
    def __init__(self, num_builders, num_fetchers, num_pushers):
        self._max_resources = {
            ResourceType.CACHE: 0,
            ResourceType.DOWNLOAD: num_fetchers,
            ResourceType.PROCESS: num_builders,
            ResourceType.UPLOAD: num_pushers,
        }

        # Resources jobs are currently using.
        self._used_resources = {
            ResourceType.CACHE: 0,
            ResourceType.DOWNLOAD: 0,
            ResourceType.PROCESS: 0,
            ResourceType.UPLOAD: 0,
        }

        # Resources jobs currently want exclusive access to. The set
        # of jobs that have asked for exclusive access is the value -
        # this is so that we can avoid scheduling any other jobs until
        # *all* exclusive jobs that "register interest" have finished
        # - which avoids starving them of scheduling time.
        self._exclusive_resources = {
            ResourceType.CACHE: set(),
            ResourceType.DOWNLOAD: set(),
            ResourceType.PROCESS: set(),
            ResourceType.UPLOAD: set(),
        }

    # reserve()
    #
    # Reserves a set of resources
    #
    # Args:
    #    resources (set): A set of ResourceTypes
    #    exclusive (set): Another set of ResourceTypes
    #    peek (bool): Whether to only peek at whether the resource is available
    #
    # Returns:
    #    (bool): True if the resources could be reserved
    #
    def reserve(self, resources, exclusive=None, *, peek=False):
        if exclusive is None:
            exclusive = set()

        resources = set(resources)
        exclusive = set(exclusive)

        # First, we check if the job wants to access a resource that
        # another job wants exclusive access to. If so, it cannot be
        # scheduled.
        #
        # Note that if *both* jobs want this exclusively, we don't
        # fail yet.
        #
        # FIXME: I *think* we can deadlock if two jobs want disjoint
        #        sets of exclusive and non-exclusive resources. This
        #        is currently not possible, but may be worth thinking
        #        about.
        #
        for resource in resources - exclusive:

            # If our job wants this resource exclusively, we never
            # check this, so we can get away with not (temporarily)
            # removing it from the set.
            if self._exclusive_resources[resource]:
                return False

        # Now we check if anything is currently using any resources
        # this job wants exclusively. If so, the job cannot be
        # scheduled.
        #
        # Since jobs that use a resource exclusively are also using
        # it, this means only one exclusive job can ever be scheduled
        # at a time, despite being allowed to be part of the exclusive
        # set.
        #
        for resource in exclusive:
            if self._used_resources[resource] != 0:
                return False

        # Finally, we check if we have enough of each resource
        # available. If we don't have enough, the job cannot be
        # scheduled.
        for resource in resources:
            if self._max_resources[resource] > 0 and self._used_resources[resource] >= self._max_resources[resource]:
                return False

        # Now we register the fact that our job is using the resources
        # it asked for, and tell the scheduler that it is allowed to
        # continue.
        if not peek:
            for resource in resources:
                self._used_resources[resource] += 1

        return True

    # release()
    #
    # Release resources previously reserved with Resources.reserve()
    #
    # Args:
    #    resources (set): A set of resources to release
    #
    def release(self, resources):
        for resource in resources:
            assert self._used_resources[resource] > 0, "Scheduler resource imbalance"
            self._used_resources[resource] -= 1
