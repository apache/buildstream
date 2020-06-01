kind: link

config:
  (?):
  - greeting == "hello":
      target: subproject.bst:subsubproject-hello-junction.bst
  - greeting == "goodbye":
      target: subproject.bst:subsubproject-goodbye-junction.bst
