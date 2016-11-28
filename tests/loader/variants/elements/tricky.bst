kind: tricky
description: |
  This element depends ambivalently on tricky-first, then specifically
  on the second variant of tricky-second. The default variant of tricky-first
  depends explicitly on the first variant of tricky-second.

  This forces the engine to make a choice and resolve the tree, we're expecting
  the tree to end up with:
    o tricky
    o tricky-first(second)
    o tricky-second(second)
depends:
- elements/tricky-first.bst
- filename: elements/tricky-second.bst
  variant: second
