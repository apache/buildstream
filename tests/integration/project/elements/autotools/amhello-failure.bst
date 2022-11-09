kind: autotools
description: An element which is meant to fail

config:
  build-commands:
    (>):
    - this-will-fail

depends:
- base.bst

sources:
- kind: tar
  url: project_dir:/files/amhello.tar.gz
  ref: 534a884bc1974ffc539a9c215e35c4217b6f666a134cd729e786b9c84af99650
