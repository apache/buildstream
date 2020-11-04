kind: import
sources:
- kind: local
  path: element.txt

#
# Depend on the subproject using a junction which overrides the
# element we're depending on, using a link to address the element
# we are overridding.
#
depends:
- subproject-override-element-using-link.bst:subelement.bst
