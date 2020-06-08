# This junction resides at the toplevel project
#
# It is used to override the subrpoject's subsubproject's
# junction to the subsubsubproject, and instead point that to
# the surpriseproject.
#
kind: junction
sources:
- kind: local
  path: surpriseproject
