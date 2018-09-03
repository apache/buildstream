class ResourceType():
    CACHE = 0
    DOWNLOAD = 1
    PROCESS = 2
    UPLOAD = 3


class Resources():
    def __init__(self, num_builders, num_fetchers, num_pushers):
        self._max_resources = {
            ResourceType.CACHE: 0,
            ResourceType.DOWNLOAD: num_fetchers,
            ResourceType.PROCESS: num_builders,
            ResourceType.UPLOAD: num_pushers
        }

        # Resources jobs are currently using.
        self._used_resources = {
            ResourceType.CACHE: 0,
            ResourceType.DOWNLOAD: 0,
            ResourceType.PROCESS: 0,
            ResourceType.UPLOAD: 0
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
            ResourceType.UPLOAD: set()
        }

    def clear_job_resources(self, job):
        for resource in job.exclusive_resources:
            self._exclusive_resources[resource].remove(hash(job))

        for resource in job.resources:
            self._used_resources[resource] -= 1

    def reserve_exclusive_resources(self, job):
        exclusive = job.exclusive_resources

        # The very first thing we do is to register any exclusive
        # resources this job may want. Even if the job is not yet
        # allowed to run (because another job is holding the resource
        # it wants), we can still set this - it just means that any
        # job *currently* using these resources has to finish first,
        # and no new jobs wanting these can be launched (except other
        # exclusive-access jobs).
        #
        for resource in exclusive:
            self._exclusive_resources[resource].add(hash(job))

    def reserve_job_resources(self, job):
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
        for resource in job.resources - job.exclusive_resources:
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
        for exclusive in job.exclusive_resources:
            if self._used_resources[exclusive] != 0:
                return False

        # Finally, we check if we have enough of each resource
        # available. If we don't have enough, the job cannot be
        # scheduled.
        for resource in job.resources:
            if (self._max_resources[resource] > 0 and
                    self._used_resources[resource] >= self._max_resources[resource]):
                return False

        # Now we register the fact that our job is using the resources
        # it asked for, and tell the scheduler that it is allowed to
        # continue.
        for resource in job.resources:
            self._used_resources[resource] += 1

        return True
