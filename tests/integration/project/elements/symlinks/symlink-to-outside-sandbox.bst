kind: manual

depends:
  - base.bst

config:
  install-commands:
    # This symlink could be used by a dependent element to trick BuildStream into
    # trying to create files outside of the sandbox.
    - mkdir "%{install-root}/opt/"
    - ln -s ../../usr "%{install-root}"/opt/escape-hatch
