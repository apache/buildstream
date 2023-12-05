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
    echo "  -s --service   Run service tests instead of regular tests"
    echo "  "
    exit 1;
}

arg_service=false

while : ; do
    case "$1" in 
	-h|--help)
	    usage;
	    shift ;;
	-s|--service)
	    arg_service=true
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
    return $?
}


# runServiceTest()
#
#  $1 = test name
#
function runServiceTest() {
    local test_name=$1

    # Run docker-compose from it's directory, because it will use
    # relative paths
    cd "${topdir}/compose"
    docker-compose \
        --env-file "${topdir}/common.env" \
        --file "${topdir}/compose/ci.${test_name}.yml" \
        up --detach --renew-anon-volumes --remove-orphans

    docker-compose \
        --env-file "${topdir}/common.env" \
        --file "${topdir}/compose/ci.docker-compose.yml" run ${test_name}
    test_exit_status=$?

    docker-compose \
        --env-file "${topdir}/common.env" \
        --file "${topdir}/compose/ci.${test_name}.yml" stop
    docker-compose \
        --env-file "${topdir}/common.env" \
        --file "${topdir}/compose/ci.${test_name}.yml" logs
    docker-compose \
        --env-file "${topdir}/common.env" \
        --file "${topdir}/compose/ci.${test_name}.yml" down --volumes

    return $test_exit_status
}


if [ -z "${test_names}" ]; then
    for test_name in mypy debian-10 fedora-37 fedora-38 fedora-39 fedora-missing-deps; do
	if ! runTest "${test_name}"; then
	    echo "Tests failed"
	    exit 1
	fi
    done
    for test_name in buildgrid buildbarn; do
	if ! runServiceTest "${test_name}"; then
	    echo "Tests failed"
	    exit 1
	fi
    done
else
    if $arg_service; then
	for test_name in ${test_names}; do
	    if ! runServiceTest "${test_name}"; then
		echo "Tests failed"
		exit 1
	    fi
	done
    else
	for test_name in ${test_names}; do
	    if ! runTest "${test_name}"; then
		echo "Tests failed"
		exit 1
	    fi
	done
    fi
fi
