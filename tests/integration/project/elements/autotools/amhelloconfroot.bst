kind: autotools
description: Autotools test

depends:
- base.bst

sources:
- kind: tar
  url: project_dir:/files/amhello.tar.gz
  ref: 534a884bc1974ffc539a9c215e35c4217b6f666a134cd729e786b9c84af99650
  directory: SourceFile

variables:
  conf-root: "%{build-root}/SourceFile"
  command-subdir: build
