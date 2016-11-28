kind: color
description: Something or other
config:
  choice: None
variants:
- variant: first
  config:
    choice: first
  depends:
  - filename: elements/tricky-second.bst
    variant: first
- variant: second
  config:
    choice: second
