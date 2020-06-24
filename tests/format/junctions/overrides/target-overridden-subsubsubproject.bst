kind: stack

# Here we depend on the target in subproject's subsubproject's
# subsubsubproject, however we've overridden the subproject's
# subsubproject's subsubsubproject with our own surprise project
#
depends:
- subproject-with-deep-override.bst:subsubproject.bst:subsubsubproject.bst:target.bst
