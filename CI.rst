Continuous integration and testing of BuildStream
=================================================

At the time of writing, BuildStream is hosted on GitLab's public website at https://gitlab.com/BuildStream/. It uses GitLab's continuous integration system to provide automated build and test of the main branch (`master`) and any branches pushed to the BuildStream repository.

As a simplification, continuous testing consists of:

* Creating a source distribution with `python3 setup.py sdist`
* Extracting that distribution
* Running `python3 setup.py test --addopts --integration`
* Extracting the coverage results and marking them as a test artifact.

These tests are run on in both Linux and Unix mode (Unix is not actually used to test Unix mode, but BST_FORCE_BACKEND: "unix" is used to test as much of that mode as we can).

Performance tests are also run in Linux mode. Performance tests operate in a different manner, do not use the source distribution, and require a special runner to keep performance tests consistent. Performance tests are performed using the separate `benchmarks` repository from https://gitlab.com/BuildStream/benchmarks and the performance test procedure is defined by that repository, not by BuildStream.

`.gitlab-ci.yml` contains the full details of the test procedure.


Requirements
============
The project must be hosted on a GitLab instance for the `.gitlab-ci.yml` script to work.

The public GitLab instance (https://gitlab.com/) has shared runners which are suitable for the functional tests. Shared runners must be enabled for the BuildStream project for this to work.

To run the performance tests, one or more reference hardware systems must act as a runner for the BuildStream project. These runners should only process jobs with the tag 'benchmarks'. They should be set up to run one job at a time. They should be set to use the `shell` Executor.

Instructions on setting up GitLab runners are provided by GitLab at https://docs.gitlab.com/runner/install/.

Assuming BuildStream and the `benchmarks` repository are both hosted on GitLab, the performance runner machines should be enabled for *both* projects. This will enable you to run continuous testing for BuildStream and also test the benchmarking repository itself and compare results.
