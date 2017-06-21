#!/bin/sh
# Shell script to set up the BuildStream Docker image.

set -eu

# We currently need a very new version of OSTree to work around some
# regressions. Once a release containing this commit is in the Fedora
# package repositories we can go back to installing OSTree with `dnf`.
OSTREE_COMMIT=9a79d13ce307d8b5b2fe0c373c5d778ad7128b5a

dnf update -y
dnf install -y bubblewrap git python3-gobject

# redhat-rpm-config seems to be needed to avoid some weird error, see:
# https://stackoverflow.com/questions/41925585/
dnf install -y gcc redhat-rpm-config

echo "Building OSTree commit $OSTREE_COMMIT"
cd
dnf install -y autoconf automake bison e2fsprogs-devel fuse-devel glib2-devel gobject-introspection-devel gpgme-devel libsoup-devel libtool openssl-devel which xz-devel zlib-devel
mkdir ostree-build ; cd ostree-build
git clone https://github.com/ostreedev/ostree ; cd ostree
git checkout $OSTREE_COMMIT
NOCONFIGURE=1 ./autogen.sh
mkdir o ; cd o
../configure --prefix=/usr
make -j 4
make install

echo "Removing OSTree build dependencies"
cd
rm -r ostree-build
dnf remove -y autoconf automake bison e2fsprogs-devel fuse-devel glib2-devel gobject-introspection-devel gpgme-devel libsoup-devel libtool openssl-devel which xz-devel zlib-devel
dnf install -y libsoup

echo "Installing latest BuildStream"
cd
git clone https://gitlab.com/BuildStream/buildstream.git ; cd buildstream
dnf install -y python3-devel
pip3 install .

echo "Removing BuildStream build dependencies"
dnf remove -y python3-devel
dnf remove -y gcc redhat-rpm-config
