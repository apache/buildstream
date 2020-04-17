kind: manual
description: |

  The statically linked hello application

# Depend on the hello library with the strict option
#
depends:
- filename: libhello.bst
  strict: true

# Stage the files/hello directory for building
sources:
  - kind: local
    path: files/hello

# Now configure the commands to run
config:

  build-commands:
  - make -f Makefile.static PREFIX="%{prefix}"

  install-commands:
  - make -f Makefile.static -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install
