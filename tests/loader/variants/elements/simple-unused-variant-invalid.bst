kind: pony
description: An element which depends on an invalid variant of a dependency
variants:
- variant: pink
  config:
    pony-color: pink
  depends:
  - filename: elements/simply-pink.bst
    variant: green
- variant: blue
  config:
    pony-color: blue
  depends:
  - elements/simply-blue.bst
