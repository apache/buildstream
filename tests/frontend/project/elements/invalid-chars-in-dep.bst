kind: stack
description: |

  This element itself has a valid name, but depends on elements that have
  invalid names. This should also result in a warning.

runtime-depends:
- invalid-chars|<>-in-name.bst
