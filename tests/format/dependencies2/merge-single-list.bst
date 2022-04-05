kind: manual
description: Depend on the same element twice, as a build and as a runtime dependency

depends:
- filename: run-build.bst
  type: runtime
- filename: run-build.bst
  type: build
