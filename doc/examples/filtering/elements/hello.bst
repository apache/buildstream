kind: manual
description: |

  The hello application

# Depend on the hello library, or the filtered version
#
(?):
- use_filter == True:
    depends:
      - libhello-filtered.bst
- use_filter == False:
    depends:
      - libhello.bst

# Stage the files/hello directory for building
sources:
  - kind: local
    path: files/hello

# Now configure the commands to run
config:

  build-commands:
  - make PREFIX="%{prefix}"

  install-commands:
  - make -j1 PREFIX="%{prefix}" DESTDIR="%{install-root}" install
