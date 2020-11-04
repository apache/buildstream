kind: junction
sources:
- kind: local
  path: subproject

config:
  overrides:
    subelement-link.bst: subproject-override-element-using-link.bst:subelement-alternative.bst
