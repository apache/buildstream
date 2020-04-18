kind: manual
description: |

  A hello world program with a custom greeting message

# Depend on the base system
depends:
- base.bst

# Stage the files/src directory for building
sources:
  - kind: local
    path: files/src

# This include file defines the %{greeting} variable used below
variables:
  (@): include/greeting.bst

# Now configure the commands to run
config:

  # This time we inform the Makefile of which greeting we want
  build-commands:
  - make PREFIX="%{prefix}" GREETING="%{greeting}"

  install-commands:
  - make -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install
