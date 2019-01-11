kind: stack
description: This element depends on two elements in different ways
build-depends:
- firstdep.bst
depends:
- filename: firstdep.bst
  type: runtime
