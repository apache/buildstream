kind: manual
description: |

  Building using freedesktop-sdk as a base

# Depend on the base system
depends:
  - freedesktop-sdk.bst:public-stacks/buildsystems.bst

# Stage the files/src directory for building
sources:
  - kind: local
    path: files/src

# Now configure the commands to run
config:

  build-commands:
  - make PREFIX="%{prefix}"

  install-commands:
  - make -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install
