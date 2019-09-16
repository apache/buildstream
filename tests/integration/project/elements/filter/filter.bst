kind: filter
depends:
- filename: filter/parent.bst
  type: build
config:
  pass-integration: True

  # `sh` is `/bin/sh`, and `/bin` is not covered by any split rule
  # As a result, to include `sh` in the image, we need to include orphans
  #
  # However we can use this to minimise the size of the artifacts, which
  # will hopefully reduce test time
  #
  include-orphans: True
  exclude:
  - runtime
