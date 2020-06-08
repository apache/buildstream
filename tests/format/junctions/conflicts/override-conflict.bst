kind: stack

#
# To trigger the conflict, we need to traverse the path of
# the overridden `subsubproject.bst` junction.
#
depends:
- subproject-override-conflicting-path.bst:subsubproject.bst:target.bst
