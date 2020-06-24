kind: junction
sources:
- kind: local
  path: subproject

#
# Here we are declaring a junction to subproject, and trying to override
# it's subproject with a deep subproject, using a different junction to
# the same subproject `subproject.bst`
#
config:
  overrides:
    subsubproject.bst: subproject.bst:subsubproject.bst:subsubsubproject.bst
