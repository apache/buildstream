#!/bin/sh

# Generate a base sysroot for running the BuildStream integration tests.
#
# The sysroot is based on freedesktop-sdk; See the project for
# details, this script only runs BuildStream and compresses the
# output.

set -eux

bst -o arch "${ARCH:-x86_64}" build base.bst
# FIXME: This should be replaced with the nice implicit compression
# resolution that will be introduced with !1451
bst -o arch "${ARCH:-x86_64}" artifact checkout base.bst --tar integration-tests-base.tar
xz integration-tests-base.tar
