kind: manual
description: |

  Building manually

# Stage the files/src directory for building
sources:
  - kind: local
    path: files/src

# Now configure the commands to run
config:

  build-commands:
  - cl hello.c
  - mkdir ..\..\..\buildstream-install
  - copy hello.exe ..\..\..\buildstream-install
