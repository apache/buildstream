#!/bin/bash
#
# A script to run a BuildStream test case.


TEST_DIR="elements/"
RESULTS="results/"
EXPECTED="expected/"

set -eu

# compare_debs
#
# Compares results to expected files for every .deb file found
#
# Args:
#    test_name ($1) - The name of the test, for error reporting
#    result_dir ($2) - The directory containing result files
#    expected_dir ($3) - The directory containing expected files
#
# Returns:
#    1 if the debs are all equivalent, 0 otherwise.
compare_debs () (
	set +e

	local test_name="$1"
	local result_dir="$2"
	local expected_dir="$3"

	# First, expected and result must have the same .deb file lists
	diff <(cd $result_dir/$test_name && find . -name "*.deb" | sort) <(cd $expected_dir/$test_name && find . -name "*.deb" | sort)
	if [ "$?" -ne 0 ]
	then
		printf "%-34s ${RED}%9s${END}\n" "$test_name" "failed"
		return 1
	fi

	for deb in $(cd $result_dir/$test_name && find . -name "*.deb"); do
		result_deb="$result_dir/$test_name/$deb"
		expected_deb="$expected_dir/$test_name/$deb"
		diff <(dpkg-deb -c $result_deb | tr -s ' ' | cut -d' ' -f6) <(dpkg-deb -c $expected_deb | tr -s ' ' | cut -d' ' -f6)
		if [ "$?" -ne 0 ]
		then
			printf "%-34s ${RED}%9s${END}\n" "$test_name" "failed"
			return 1
		fi
	done
	printf "%-34s ${GREEN}%9s${END}\n" "$test_name" "succeeded"
	return 0
)

# run_test
#
# Run tests for this test case.
#
# This should create a set of directories that match the directories
# in 'results/', as well as a log of the BuildStream output in
# 'test_log.log'.
#
run_test () {
	local element
	local elements
	local element_name
	local test_dir
	local bst_file
	local tar_file

	local successes=0
	local total=0
	local exit

	source ../lib.sh

	mkdir -p "$TEST_DIR"
	elements="$(find "$TEST_DIR" -maxdepth 1 -type f)"

	for element in $elements;
	do
		total=$((total + 1))

		element_name="$(basename "$element")"
		element_name="${element_name%.*}"

		test_dir="$RESULTS/$element_name"

		echo "Running test '$element_name'"

		bst_with_flags build "$element_name".bst
		echo "Built $element_name"
		bst_with_flags checkout "$element_name".bst "$test_dir"

		exit=0
		if [ "$element" == "dpkg-deploy-test.bst" ]; then
			compare_debs "$element_name" "$RESULTS" "$EXPECTED" || exit=$?
		else
			compare_results_no_contents "$element_name" "$RESULTS" "$EXPECTED" || exit=$?
		fi
		if [ $exit == 0 ]
		then
		   successes=$((successes + 1))
		fi
	done

	if [ $total != $successes ]
	then
		return 1
	fi
}

run_test "$@"
