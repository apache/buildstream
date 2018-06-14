kind: import

description: |
  Alpine Linux base

sources:
- kind: tar
  # A little more work is required to support multiple architectures
  # More information can be found here:
  # https://buildstream.gitlab.io/buildstream/projectconf.html#architecture
  url: alpine:integration-tests-base.v1.x86_64.tar.xz
  ref: 3eb559250ba82b64a68d86d0636a6b127aa5f6d25d3601a79f79214dc9703639
