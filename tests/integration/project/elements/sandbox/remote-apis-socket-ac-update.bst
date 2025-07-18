kind: manual

depends:
  - filename: base.bst
    type: build

sandbox:
  remote-apis-socket:
    path: /tmp/reapi.sock
    action-cache-enable-update: true

config:
  build-commands:
    - test -S /tmp/reapi.sock
