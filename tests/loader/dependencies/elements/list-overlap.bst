kind: stack
description: This element depends on two elements in different ways
build-depends:
- elements/firstdep.bst
depends:
- filename: elements/firstdep.bst
  type: runtime
