kind: compose
depends:
- filename: base.bst
  type: build
public:
  bst:
    integration-commands:
    - touch /foo
config:
  # `sh` is `/bin/sh`, and `/bin` is not covered by any split rule
  # As a result, to include `sh` in the image, we need to include orphans
  #
  # However we can use this to minimise the size of the artifacts, which
  # will hopefully reduce test time
  #
  include-orphans: True
  include:
  - runtime
  exclude:
  - runtime
