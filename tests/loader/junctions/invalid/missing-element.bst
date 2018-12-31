# This refers to the `foo.bst` element through
# the `base.bst` junction. The `base.bst` junction
# exists but the `foo.bst` element does not exist
# in the subproject.
#
kind: stack
depends:
- junction: base.bst
  filename: foo.bst
