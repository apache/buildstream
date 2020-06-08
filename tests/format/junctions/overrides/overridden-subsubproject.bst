# This junction resides at the toplevel project
#
# It is used to override the subrpoject's junction to
# the subsubproject, and instead point that to the
# subsubsubproject.
#
kind: junction
sources:
- kind: local
  path: subproject/subsubproject/subsubsubproject
