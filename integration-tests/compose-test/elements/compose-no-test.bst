kind: compose

depends:
  - filename: dependencies/amhello.bst
    type: build
  - filename: dependencies/amhello-run.bst
    type: build

config:
  include:
    - runtime
    - devel
    - debug
    - doc
    - locale
