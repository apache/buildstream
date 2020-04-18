kind: compose

# Dependencies of a compose element cannot be transient,
# we can only build-depend on the inputs of a composition.
#
build-depends:
- hello.bst

config:

  # Only include files from the runtime domain
  #
  include:
  - runtime

  # Don't include any files which do not match any existing
  # split rule domains.
  #
  include-orphans: False

  # Run integration commands before composition
  #
  integrate: True
