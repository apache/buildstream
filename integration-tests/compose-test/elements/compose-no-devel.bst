kind: compose

depends:
  - filename: dependencies/amhello.bst
    type: build
  - filename: dependencies/devel-run.bst
    type: build

config:
  include:
    - runtime
    - debug
    - doc
    - locale
