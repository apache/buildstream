kind: stack

# Similar test as target-overridden-subsubproject.bst, but we
# test that this works equally if we are referring to a subsubproject
# which is in fact a link.
#
depends:
- subproject-with-overridden-link.bst:subsubproject-link.bst:target.bst
