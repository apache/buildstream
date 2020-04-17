kind: import
description: |

    Alpine Linux base runtime

sources:
- kind: tar
  url: alpine:integration-tests-base.v1.x86_64.tar.xz
  ref: 3eb559250ba82b64a68d86d0636a6b127aa5f6d25d3601a79f79214dc9703639

public:
  bst:
    #
    # Run ldconfig in the libdir before running anything
    #
    integration-commands:
    - ldconfig "%{libdir}"

    #
    # Extend the runtime split-rule domain for this element,
    # such that we capture the runtime linker.
    #
    # There are various other things provided by this runtime
    # such as tooling in /bin and an installation of python
    # and perl, but we'll overlook these for the sake of
    # this example.
    #
    split-rules:
      runtime:
        (>):
        - "/lib/ld*.so*"
