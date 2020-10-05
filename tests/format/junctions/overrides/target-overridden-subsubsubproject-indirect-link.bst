kind: stack

# Similar test as target-overridden-subsubsubproject.bst, except that
# we use links in the addressing of overrides.
#
depends:
- subproject-with-deep-override-indirect-link.bst:subsubproject.bst:subsubsubproject.bst:target.bst
