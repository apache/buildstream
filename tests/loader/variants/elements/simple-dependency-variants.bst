kind: pony
description: Simple dependency variants, different variants depend on different elements
variants:
- variant: pink
  config:
    pony-color: pink
  depends:
  - elements/simply-pink.bst
- variant: blue
  config:
    pony-color: blue
  depends:
  - elements/simply-blue.bst
