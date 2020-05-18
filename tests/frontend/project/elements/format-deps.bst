kind: import

description: >
  It is important that this element has both and build and runtime dependencies.
  It is also important that it has a dependency that is needed at both build
  time and runtime.

sources:
- kind: local
  path: files/etc-files

depends:
- import-links.bst
build-depends:
- import-dev.bst
runtime-depends:
- import-bin.bst
