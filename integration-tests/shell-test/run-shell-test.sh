#!/bin/bash
#
# A script to run a BuildStream test case.

ECHO_TEST_KEY="1234567890abcdefghijklmnopqrstuvwzyz"

set -eu
source ../lib.sh

assert_expected_key () {

	local test_name=$1
	local success=0

	# Assert that the test key we echoed in our runtime made it to stdout and that we
	# captured it in the output file.
	if ! grep "${ECHO_TEST_KEY}" shell.out > /dev/null
	then
	    success=1
	else
	    success=0
	fi

	report_results "$test_name" $success
	return $success
}

# run_test
#
# Run tests for this test case.
#
run_test () {
	local success=0

	bst_with_flags build "dependencies/base-platform.bst"

	bst_with_flags shell "dependencies/base-platform.bst" -- sh -c "echo ${ECHO_TEST_KEY}" | tee shell.out
	assert_expected_key 'sh -c "echo ${ECHO_TEST_KEY}"'
	if [ $? -ne 0 ]; then
	    success=1
	fi

	bst_with_flags shell "dependencies/base-platform.bst" -- /bin/echo ${ECHO_TEST_KEY} | tee shell.out
	assert_expected_key "/bin/echo ${ECHO_TEST_KEY}"
	if [ $? -ne 0 ]; then
	    success=1
	fi

	bst_with_flags shell "dependencies/base-platform.bst" -- sh -c "printf \"${ECHO_TEST_KEY}\n\"" | tee shell.out
	assert_expected_key 'sh -c "printf \"${ECHO_TEST_KEY}\n\""'
	if [ $? -ne 0 ]; then
	    success=1
	fi

	return $success
}

run_test "$@"
