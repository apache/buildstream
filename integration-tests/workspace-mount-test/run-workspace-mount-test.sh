#!/bin/bash
#
# A script to run a BuildStream test case.


TEST_DIR="elements/"

set -eu

# run_test
#
# Run tests for this test case.
#
run_test () {
    local element
    local workspace_dir

    source ../lib.sh

    mkdir -p "$TEST_DIR"
    element=workspace-mount-test.bst
    workspace_dir="$TEST_DIR"workspace-dir

    bst_with_flags workspace open "$element" "$workspace_dir"
    bst_with_flags build "$element"
    if [ ! -f "$workspace_dir/hello.o" ]; then
        return 1
    fi
}

run_test "$@"
