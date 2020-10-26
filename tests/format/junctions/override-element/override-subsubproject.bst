kind: import
sources:
- kind: local
  path: element.txt
  
#
# Depend on the subsubproject element, and override it's dependency, the intermediate
# project also overrides the same subsubproject element, and this test ensures
# that the toplevel override takes precedence.
#
depends:
- subproject-override-subsubproject-element.bst:subsubproject-override-dep.bst:subsubelement.bst
