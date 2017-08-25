#!/bin/sh
# Shell script to set up the BuildStream Docker image.

set -eu

dnf update -y
dnf install -y bubblewrap git python3-gobject bzr ostree

# redhat-rpm-config seems to be needed to avoid some weird error, see:
# https://stackoverflow.com/questions/41925585/
dnf install -y gcc redhat-rpm-config

echo "Installing latest BuildStream"
cd
git clone https://gitlab.com/BuildStream/buildstream.git ; cd buildstream
dnf install -y python3-devel
pip3 install .

echo "Removing BuildStream build dependencies"
dnf remove -y python3-devel
dnf remove -y gcc redhat-rpm-config
dnf clean all
