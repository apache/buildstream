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
	local bst_file1
	local bst_file2
	local tar_file

	local successes=0
	local total=0
	local exit

	source ../lib.sh

	tar_file="$(dirname "$(readlink -f "$0")")/src/amhello.tar.gz"
	bst_file1="$(dirname "$(readlink -f "$0")")/elements/dependencies/amhello.bst"
	bst_file2="$(dirname "$(readlink -f "$0")")/elements/dependencies/amhello-full.bst"

	patch_file_location "$bst_file1" "$tar_file"
	patch_file_location "$bst_file2" "$tar_file"

	# Get rid of .gitkeep files
	find . -name ".gitkeep" -exec rm {} \;

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
		bst_with_flags checkout "$element_name".bst "$test_dir"

		# XXX Special case for compose-integration-remove, dont
		#     use the automated compare_results for this because
		#     we dont want to commit a huge result set to compare
		#
		#     Instead just check for the presence of some files
		#     and assert that the result has properly removed some
		#     files due to integration commands removing them.
		#
		if [ "${element_name}" == "compose-integration-remove" ]; then
		    if [ -e "${test_dir}/usr/share/doc/amhello" ]; then
			# This is a failure if the directory which was removed
			# by the integration commands still exists
			exit=1
		    else
			exit=0
		    fi
		    report_results "${element_name}" $exit
		else
		    # The rest of the tests here use the weird comparison
		    # of exactness in the checkout results
		    exit=0
		    compare_results "$element_name" "$RESULTS" "$EXPECTED" || exit=$?
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
