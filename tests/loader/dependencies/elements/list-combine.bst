kind: stack
description: This element depends on three elements in different ways
build-depends:
- elements/firstdep.bst
runtime-depends:
- elements/seconddep.bst
depends:
- elements/thirddep.bst
