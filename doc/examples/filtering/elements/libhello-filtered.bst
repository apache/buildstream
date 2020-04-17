kind: filter
description: |

  A filtered version of libhello which excludes the defaults

# Specify the build dependency to filter
build-depends:
- libhello.bst

# Propagate runtime dependencies
runtime-depends:
- base.bst

# Now configure the commands to run
config:
  exclude:
  - defaults
