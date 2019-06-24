kind: import
description: |

    Freedesktop-sdk base runtime

sources:
- kind: tar
  url: freedesktop:integration-tests-base.v3.x86_64.tar.xz
  ref: 5593c0a269291890b466775520e34f90800fc6760abd4ab804a13fe9b824a17c
  base-dir: ''

#
# Run ldconfig in the libdir before running anything
#
public:
  bst:
    integration-commands:
    - ldconfig "%{libdir}"
