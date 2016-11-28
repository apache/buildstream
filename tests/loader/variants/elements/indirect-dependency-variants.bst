kind: pony
description: |
  Indirect dependency variants, depend on a different variant of the simple test,
  depending on the selected variant
variants:
- variant: blue
  config:
    pony-color: blue
  depends:
  - filename: elements/simple-dependency-variants.bst
    variant: blue
- variant: pink
  config:
    pony-color: pink
  depends:
  - filename: elements/simple-dependency-variants.bst
    variant: pink
