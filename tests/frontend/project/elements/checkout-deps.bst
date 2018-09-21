kind: import
description: It is important for this element to have both build and runtime dependencies
sources:
- kind: local
  path: files/etc-files
depends:
- filename: import-dev.bst
  type: build
- filename: import-bin.bst
  type: runtime
