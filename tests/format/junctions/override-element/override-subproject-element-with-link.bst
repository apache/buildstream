kind: import
sources:
- kind: local
  path: element.txt

#
# Depend on the subproject using a junction which overrides the
# element we're depending on, with a local link to an alternative
# element in that same subproject.
#
depends:
- subproject-override-element-with-link.bst:subelement.bst
