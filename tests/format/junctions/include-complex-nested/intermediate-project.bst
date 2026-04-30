kind: junction

sources:
- kind: local
  path: intermediate-project

config:
  overrides:
    subproject.bst:placeholder.bst: alternative-placeholder.bst

  options:
    animal: '%{animal}'
