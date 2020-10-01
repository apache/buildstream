kind: junction
sources:
- kind: local
  path: subproject

config:
  overrides:
    subsubproject-link.bst:subsubsubproject.bst: overridden-subsubsubproject.bst
