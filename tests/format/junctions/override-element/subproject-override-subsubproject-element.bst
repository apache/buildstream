kind: junction
sources:
- kind: local
  path: subproject

config:
  overrides:
    subsubproject-override-dep.bst:subsubdependency.bst: subdep-override.bst
