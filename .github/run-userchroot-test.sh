#!/bin/bash

export BST_CAS_STAGING_ROOT="/builds/userchroot"

# Use buildbox-run-userchroot and hardlinking
sudo ln -svf buildbox-run-userchroot /usr/local/bin/buildbox-run
sudo rm -vf /usr/local/bin/buildbox-fuse

# When using userchroot, buildbox-casd must run as a separate user
sudo useradd -g testuser buildbox-casd
sudo chown buildbox-casd:testuser /usr/local/bin/buildbox-casd
sudo chmod u+s /usr/local/bin/buildbox-casd

# Set up staging root with permissions required by userchroot,
# must be on same filesystem as current directory to support hardlinks
sudo mkdir -p "${BST_CAS_STAGING_ROOT}"
sudo chown -R buildbox-casd:testuser "${BST_CAS_STAGING_ROOT}"
# userchroot doesn't allow group/world-writable base directory
sudo chmod go-w /builds
echo buildbox-casd:${BST_CAS_STAGING_ROOT} | sudo tee /etc/userchroot.conf

# Created files must be writable by the group (i.e. both bst and buildbox-casd)
umask 002
tox -vvvvv -- --color=yes --integration
