kind: manual
description: |

  This is an invalid non strict dependency because it is
  currently illegal to explicitly set a dependency to be
  non-strict (even though this is the default).

depends:
- filename: firstdep.bst
  strict: false
