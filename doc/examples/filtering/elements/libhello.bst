kind: manual
description: |

  The libhello library

# Depend on the base system
depends:
- base.bst

# Stage the files/libhello directory for building
sources:
  - kind: local
    path: files/libhello

# Now configure the commands to run
config:

  build-commands:
  - make PREFIX="%{prefix}"

  install-commands:
  - make -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install

public:
  bst:
    # Define a split domain which captures the defaults
    # which this library installs into %{datadir}
    #
    split-rules:
      defaults:
      - "%{datadir}/libhello/default-person.txt"
