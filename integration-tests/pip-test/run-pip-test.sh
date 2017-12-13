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

	tar_file="$(dirname "$(readlink -f "$0")")/src/hello.tar.xz"
	bst_file="$(dirname "$(readlink -f "$0")")/elements/hello.bst"

	patch_file_location "$bst_file" "$tar_file"

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
		bst_checkout "$element_name".bst "$test_dir"

		exit=0

		# Unfortunately the order written by Pip is not deterministic
		# https://github.com/pypa/pip/pull/4667
		for FILE in $(find "$RESULTS" -name 'installed-files.txt'); do
			LC_ALL=C sort "$FILE" > "$FILE.tmp"
			mv "$FILE.tmp" "$FILE"
		done

		compare_results "$element_name" "$RESULTS" "$EXPECTED" || exit=$?
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
