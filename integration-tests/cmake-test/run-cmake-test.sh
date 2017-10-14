#!/bin/bash
#
# A script to run a BuildStream test case.


TEST_DIR="elements/"
RESULTS="results/"
EXPECTED="expected/"

set -eu

# run_test
#
# Run tests for this test case.
#
# This test has more manual intervention since it creates binary files
# which may change.
#
run_test () {
	local bst_file
	local tar_file

	local successes=0
	local total=2
	local exit

	source ../lib.sh

	###############################################################
	### Setup
	###############################################################

	tar_file="$(dirname "$(readlink -f "$0")")/src/step7.tar.gz"
	bst_file="$(dirname "$(readlink -f "$0")")/elements/step7.bst"

	patch_file_location "$bst_file" "$tar_file"

	mkdir -p "$TEST_DIR"

	###############################################################
	### Run tests
	###############################################################

	## Test step7
	echo "Running test 'step7'"

	bst_with_flags build "step7.bst"
	bst_with_flags checkout "step7.bst" "results/step7"

	# Remove changing binary file
	rm results/step7/usr/bin/libMathFunctions.a

	exit=0
	diff -r "$RESULTS/step7" "$EXPECTED/step7" || exit=$?
	if [ $exit == 0 ]
	then
		successes=$((successes + 1))
		printf "%-34s ${GREEN}%9s${END}\n" "step7" "succeeded"
	else
		echo "Error: Unexpected or missing file in 'results/step7'"
		printf "%-34s ${RED}%9s${END}\n" "step7" "failed"
	fi

	## Test step7-run
	echo "Running test 'step7-run'"

	bst_with_flags build "step7-run.bst"
	bst_with_flags checkout "step7-run.bst" "results/step7-run"

	exit=0
	compare_results "step7-run" "results" "expected" || exit=$?
	if [ $exit == 0 ]
	then
		successes=$((successes + 1))
	else
		echo "Error: Unexpected or missing file in 'results/step7'"
	fi

	###############################################################
	### Check results
	###############################################################

	if [ $total != $successes ]
	then
		return 1
	fi
}

run_test "$@"
