kind: import
description: |
  Dependency element providing dep.h header.
  Changing the header content triggers rebuilds of downstream
  elements while their weak keys remain stable.

sources:
- kind: local
  path: files/speculative/dep-files
