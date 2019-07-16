kind: script
description: |

  Main target for tests/frontend/pull.py::test_push_pull_non_strict().
  We do not use target.bst as we want an element kind that supports
  build dependencies.

build-depends:
- import-bin.bst
- compose-all.bst
