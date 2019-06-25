kind: import

description: |
  Freedesktop-sdk base for tests

  Generated using the `tests/integration-tests/base/generate-base.sh` script.

sources:
  - kind: tar
    base-dir: ''
    (?):
    - arch == "x86-64":
        ref: 5593c0a269291890b466775520e34f90800fc6760abd4ab804a13fe9b824a17c
        url: "freedesktop:integration-tests-base.v3.x86_64.tar.xz"
    - arch == "aarch64":
        ref: 93c62d0d1f400dc37db8ceee122719ffa951d929b7fad684965057ffaeaf2b73
        url: "freedesktop:integration-tests-base.v3.aarch64.tar.xz"
