kind: manual

depends:
  - base.bst
  - symlinks/symlink-to-outside-sandbox.bst

config:
  install-commands:
    # The element we depend on has installed a relative symlink to
    # `/opt/escape-hatch` which uses `../` path sections so that its
    # target points outside of the sandbox.
    #
    # This element installs a directory to the same `/opt/escape-hatch`
    # location and installs a file inside the directory.
    #
    # When this element is staged on top of its dependency, the directory will
    # overlap with the symlink and will thus be ignored. BuildStream will then
    # try to install the `etc/org.conf` file inside the symlinks target and
    # will end up with a path like `../../usr/etc/org.conf`.
    #
    # This could in theory overwrite something on the host system. In practice
    # the normal UNIX permissions model should prevent any damage, but we
    # should still detect this happening and raise an error as it is a sure
    # sign that something is wrong.
    #
    - mkdir -p "%{install-root}"/opt/escape-hatch/etc/
    - echo "example" > "%{install-root}"/opt/escape-hatch/etc/org.conf
