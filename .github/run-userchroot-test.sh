#!/bin/bash

export BST_CAS_STAGING_ROOT="/builds/userchroot"

# Use buildbox-run-userchroot and hardlinking
ln -svf buildbox-run-userchroot /usr/local/bin/buildbox-run
rm -vf /usr/local/bin/buildbox-fuse

# When using userchroot, buildbox-casd must run as a separate user
useradd -g testuser buildbox-casd
chown buildbox-casd:testuser /usr/local/bin/buildbox-casd
chmod u+s /usr/local/bin/buildbox-casd

# Set up staging root with permissions required by userchroot,
# must be on same filesystem as current directory to support hardlinks
mkdir -p "${BST_CAS_STAGING_ROOT}"
chown -R buildbox-casd:testuser "${BST_CAS_STAGING_ROOT}"
# userchroot doesn't allow group/world-writable base directory
chmod go-w /builds
echo buildbox-casd:${BST_CAS_STAGING_ROOT} > /etc/userchroot.conf

# Run as regular user after setting up the environment.
# Use umask as created files must be writable by the group (i.e. both bst and buildbox-casd)
su testuser -c "umask 002 && tox -vvvvv -- --color=yes --integration -x"

cat .tox/*/tmp/*/cache/logs/_casd/*

exit 1
