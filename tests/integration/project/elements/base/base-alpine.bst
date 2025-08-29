kind: import

description: |
  Alpine Linux base for tests

  Generated using the `tests/integration-tests/base/generate-base.sh` script.

sources:
  - kind: tar
    base-dir: ''
    (?):
    - arch == "x86-64":
        ref: 3eb559250ba82b64a68d86d0636a6b127aa5f6d25d3601a79f79214dc9703639
        url: "test-images:integration-tests-base.v1.x86_64.tar.xz"
    - arch == "aarch64":
        ref: 431fb5362032ede6f172e70a3258354a8fd71fcbdeb1edebc0e20968c792329a
        url: "test-images:integration-tests-base.v1.aarch64.tar.xz"
