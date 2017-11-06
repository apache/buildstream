#!/bin/bash

set -u

GREEN="\e[0;32m"
YELLOW="\e[0;33m"
RED="\e[0;31m"
END="\e[0m"

usage () {
	cat <<EOF
Usage:
	run-test.sh [-h|--help] [-a <arg>|--arg <arg>] <command> [<args>]

Run various commands to test bst.

Commands:

	test	Run the test suite. If no arguments are given, the full
                suite is run, otherwise the given arguments will be run
	run	Run the test suite.  (Does not clean)
	clean	Clean temporary test files

Options:
	--help  	Display this help message and exit
	--arg   	Specify an argument for bst, such as --colors
	--cov   	Specify a coverage rcfile
	--sources	Specify a location for the source cache
EOF
}

BST_COVERAGE=
BST_FLAGS=
BST_SOURCE_CACHE=
export BST_COVERAGE
export BST_FLAGS
export BST_SOURCE_CACHE

main () {
	while : ;
	do
		case "${1:-}" in
			"test")
				shift
				configure
				clean "$@"
				run "$@"
				break ;;
			"run")
				shift
				configure
				run "$@"
				break ;;
			"clean")
				shift
				clean "$@"
				break ;;
			--sources)
				export BST_SOURCE_CACHE=$(realpath -m "${2}")
				shift 2 ;;
			-c|--cov)
				export BST_COVERAGE=$(realpath -m "${2}")
				shift 2 ;;
			-a|--arg)
				export BST_FLAGS="${BST_FLAGS:-} $2"
				shift 2 ;;
			-h|--help)
				usage
				break ;;
			*)
				echo "Error: Unrecognized argument '${1:-}'" 1>&2
				usage
				break ;;
		esac
	done
}


# configure
#
# Creates the buildstream.conf configuration
configure () {
    	# Treat source cache specially, we want to reuse it when
	# running automated CI
	if [ -z "${BST_SOURCE_CACHE}" ]; then
	    BST_SOURCE_CACHE="$(pwd)/tmp/sources"
	fi

        # Create buildstream.conf
        cat > "$(pwd)/buildstream.conf" <<EOF
sourcedir: "${BST_SOURCE_CACHE}"
builddir: "$(pwd)/tmp/build"
artifactdir: "$(pwd)/tmp/artifacts"
logdir: "$(pwd)/tmp/logs"
EOF
        CONFIG_LOCATION="$(pwd)/buildstream.conf"
        export CONFIG_LOCATION
}


# run
#
# Run all tests in the current directory.
run () {
	local succeeded=0
	local failed=0
	local state
	local tests
	local dir

	if [ $# -ge 1 ];
	then
		tests=$@
	else
		tests="*"
	fi

	for dir in $tests;
	do
		if [ -d "$dir" ] && [ "$dir" != "tmp" ]
		then
			run-test "$dir"
			state=$?
			if [ $state == 0 ]
			then
				((succeeded++))
			else
				((failed++))
			fi
		fi
	done

	if [ ! -z "${BST_COVERAGE}" ]; then
	    if [ -f .coverage ]; then
		rm -f .coverage
	    fi

	    for file in $(find . -name ".coverage.*"); do
		coverage combine -a ${file}
	    done
	    coverage report -m
	fi

	echo
	printf "%4s test%.*s ${GREEN}succeeded${END}.\n" $succeeded $((succeeded != 1)) "s"
	printf "%4s test%.*s ${RED}failed${END}.\n" $failed $((failed != 1)) "s"

	if [ $failed != 0 ]
	then
	   exit 1
	fi
}

# clean
#
# Clean all tests in the current directory.
clean () {
	local dir

	for dir in *;
	do
		if [ -d "$dir" ]
		then
			(cd "$dir" || exit 1
			 rm -rf "results/"*
			 rm -rf ".bst/"
			 rm -rf "$(pwd)/tmp/")
		fi
	done
}

# run-test
#
# Run the test in the given directory
#
# Args:
#    test ($1) - The test to run
#
run-test () {
	local test="$1"

	echo "============================================================"
	echo "Running tests for test case '$test'"
	echo "============================================================"

	(cd "$test" || exit 1
	 bash "run-$(basename "$test").sh")

	if [ ! "$?" -eq 0 ]
	then
		echo -e "Tests for '$test' ${RED}failed${END}.\n" 2>&1
		return 1
	fi
}

main "$@"
