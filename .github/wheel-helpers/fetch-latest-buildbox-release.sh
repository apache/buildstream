#!/bin/bash

# Download latest release binaries of BuildBox. These are statically linked
# binaries produced by the buildbox-integration GitLab project, which we
# bundle into BuildStream wheel packages.

set -eux

#
# For now we only support building wheels for linux x86_64 linked against glibc
#
tarball="buildbox-x86_64-linux-gnu.tgz"

curl -L -O "https://gitlab.com/buildgrid/buildbox/buildbox-integration/-/releases/permalink/latest/downloads/${tarball}"

mkdir -p src/buildstream/subprojects/buildbox
tar --extract --file "./${tarball}" --directory src/buildstream/subprojects/buildbox

cd src/buildstream/subprojects/buildbox
rm buildbox-run
mv buildbox-run-bubblewrap buildbox-run
