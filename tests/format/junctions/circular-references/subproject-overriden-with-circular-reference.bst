kind: junction
sources:
- kind: local
  path: subproject

config:
  overrides:
    subsubproject.bst: subproject-overriden-with-circular-reference.bst:subsubproject.bst:subsubsubproject.bst
