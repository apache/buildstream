#!/bin/sh
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

# Generate a base sysroot for running the BuildStream integration tests.
#
# The sysroot is based off the Alpine Linux distribution. The script downloads
# a release of Alpine, sets up a cheap container using `bwrap` and installs the
# packages that are needed by the integration tests, then outputs a .tar.xz
# file.

set -eux

ALPINE_ARCH=${ARCH:-x86-64}
ALPINE_BASE=http://dl-cdn.alpinelinux.org/alpine/v3.7/releases/${ALPINE_ARCH}/alpine-minirootfs-3.7.0-${ALPINE_ARCH}.tar.gz

mkdir root

wget ${ALPINE_BASE} -O alpine-base.tar.gz

tar -x -f ./alpine-base.tar.gz -C ./root --exclude dev/\*

run() {
    # This turns the unpacked rootfs into a container using Bubblewrap.
    # The Alpine package manager (apk) calls `chroot` when running package
    # triggers so we need to enable CAP_SYS_CHROOT. We also have to fake
    # UID 0 (root) inside the container to avoid permissions errors.
    bwrap --bind ./root / --dev /dev --proc /proc --tmpfs /tmp \
          --ro-bind /etc/resolv.conf /etc/resolv.conf \
          --setenv PATH "/usr/bin:/usr/sbin:/bin:/sbin" \
          --unshare-user --uid 0 --gid 0 \
          --cap-add CAP_SYS_CHROOT \
          /bin/sh -c "$@"
}

# Enable testing repo for Tiny C Compiler package
run "echo http://dl-cdn.alpinelinux.org/alpine/edge/testing >> /etc/apk/repositories"

# Fetch the list of Alpine packages.
run "apk update"

# There are various random errors from `apk add` to do with ownership, probably
# because of our hacked up `bwrap` container. The errors seem harmless so I am
# just ignoring them.
set +e

# Install stuff needed by all integration tests that compile C code.
#
# Note that we use Tiny C Compiler in preference to GCC. There is a huge
# size difference -- 600KB for TinyCC vs. 50MB to 100MB for GCC. TinyCC
# supports most of the ISO C99 standard, but has no C++ support at all.
run "apk add binutils libc-dev make tcc"
run "ln -s /usr/bin/tcc /usr/bin/cc"

# Install stuff for tests/integration/autotools
run "apk add autoconf automake"

# Install stuff for tests/integration/cmake
run "apk add cmake"

# Install stuff for tests/integration/pip
run "apk add python3"

set -e

# Cleanup the package cache
run "rm -R /var/cache/apk"

tar -c -v -J -f integration-tests-base.tar.xz -C root .
