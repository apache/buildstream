kind: stack
description: It is important for this element to have both build and runtime dependencies
depends:
- filename: import-dev.bst
  type: build
- filename: import-bin.bst
  type: runtime
