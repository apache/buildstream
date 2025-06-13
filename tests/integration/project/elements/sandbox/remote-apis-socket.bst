kind: manual

depends:
  - filename: base.bst
    type: build

sandbox:
  remote-apis-socket:
    path: /tmp/reapi.sock

config:
  build-commands:
    - test -S /tmp/reapi.sock
