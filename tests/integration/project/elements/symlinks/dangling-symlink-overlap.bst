kind: manual

depends:
  - base.bst
  - symlinks/dangling-symlink.bst

config:
  install-commands:
    # The element that we depend on installs a symlink at `/opt/orgname`,
    # which points to a non-existant target of `/usr/orgs/orgname`.
    # BuildStream converts absolute symlink targets into relative ones so it
    # ends up pointing to ../usr/orgs/orgname, but this resolves to the same
    # place.

    # This element creates a directory at `/opt/orgname` and installs files
    # inside it. When this element is staged on top of the dependency this
    # directory will be ignored as the symlink will already be there;
    # BuildStream will then process the files that should be /in/ the
    # directory. The expected behaviour when installing files within a symlink
    # is to install them within the symlink's target, so the file
    # `/opt/orgname/etc/org.conf` should end up at
    # `/usr/orgs/orgname/etc/org.conf`. And since that directory doesn't exist
    # BuildStream will also need to create it before installing anything there.
    #
    - mkdir -p "%{install-root}"/opt/orgname/etc/
    - echo "example" > "%{install-root}"/opt/orgname/etc/org.conf
