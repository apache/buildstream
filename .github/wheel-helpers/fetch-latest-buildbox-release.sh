#!/bin/bash

# Download latest release binaries of BuildBox. These are statically linked
# binaries produced by the buildbox-integration GitLab project, which we
# bundle into BuildStream wheel packages.

set -eux

wget https://gitlab.com/buildgrid/buildbox/buildbox-integration/-/releases/permalink/latest/downloads/binaries.tgz

mkdir -p src/buildstream/subprojects/buildbox
tar --extract --file ./binaries.tgz --directory src/buildstream/subprojects/buildbox

cd src/buildstream/subprojects/buildbox
rm buildbox-run
mv buildbox-run-bubblewrap buildbox-run
