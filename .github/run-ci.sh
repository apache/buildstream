#!/bin/bash

topdir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

function usage () {
    echo "Usage: "
    echo "  run-ci.sh [OPTIONS] [TEST NAME [TEST NAME...]]"
    echo
    echo "Runs the CI tests locally using docker"
    echo
    echo "The test names are based on the names of tests in the CI yaml files"
    echo
    echo "If no test names are specified, all tests will be run"
    echo
    echo "Options:"
    echo
    echo "  -h --help      Display this help message and exit"
    echo "  "
    exit 1;
}

while : ; do
    case "$1" in
	-h|--help)
	    usage;
	    shift ;;
	*)
	    break ;;
    esac
done

test_names="${@}"


# We need to give ownership to the docker image user `testuser`,
# chances are high that this will be the same UID as the primary
# user on this host
#
user_uid="$(id -u)"
user_gid="$(id -g)"
if [ "${user_uid}" -ne "1000" ] || [ "${user_gid}" -ne "1000" ]; then
    sudo chown -R 1000:1000 "${topdir}/.."
fi


# runTest()
#
#  $1 = test name
#
function runTest() {
    test_name=$1

    # Run docker-compose from it's directory, because it will use
    # relative paths
    cd "${topdir}/compose"
    docker-compose \
        --env-file ${topdir}/common.env \
        --file ${topdir}/compose/ci.docker-compose.yml \
        run "${test_name}"
}


# Lazily ensure that the script exits when a command fails
#
set -e

if [ -z "${test_names}" ]; then
    runTest "lint"
    runTest "debian-10"
    runTest "fedora-36"
    runTest "fedora-37"
else
    for test_name in "${test_names}"; do
	runTest "${test_name}"
    done
fi
