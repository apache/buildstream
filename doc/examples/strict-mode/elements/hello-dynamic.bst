kind: manual
description: |

  The dynamically linked hello application

# Depend on the hello library
depends:
- libhello.bst

# Stage the files/hello directory for building
sources:
  - kind: local
    path: files/hello

# Now configure the commands to run
config:

  build-commands:
  - make -f Makefile.dynamic PREFIX="%{prefix}"

  install-commands:
  - make -f Makefile.dynamic -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install
