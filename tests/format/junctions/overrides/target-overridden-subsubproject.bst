kind: stack

# Here we depend on the target in subproject's subsubproject,
# however we've overridden the subproject's subsubproject with
# our own.
#
# We should still be able to address that overridden subproject
# and access the project we've overridden it with, which will
# turn out to be the subsubsubproject.
#
depends:
- subproject-with-override.bst:subsubproject.bst:target.bst
