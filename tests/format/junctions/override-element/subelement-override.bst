kind: import
sources:
- kind: local
  path: subelement-override.txt

# We override the subproject direct dependency with this element,
# and this element explicitly depends on it's dependency in that
# subproject.
#
# The dependency we depend on happens to be the same dependency
# as the element we are overridding.
#
depends:
- subproject-override-element.bst:subdependency.bst
