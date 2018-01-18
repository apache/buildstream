kind: manual

depends:
  - base.bst

config:
  install-commands:
    # The installed file `/opt/orgname` will be a symlink to a directory that
    # doesn't exist (`/usr/orgs/orgname`). BuildStream should store this as a
    # relative symlink; among other reasons, if we ever stage an absolute
    # symlinks then we risk subsequent operations trying to write outside the
    # sandbox to paths on the host.
    - mkdir -p "%{install-root}"/opt/
    - ln -s /usr/orgs/orgname "%{install-root}"/opt/orgname
