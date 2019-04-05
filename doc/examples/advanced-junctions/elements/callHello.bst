kind: import

sources:
- kind: local
  path: files/callHello.sh

depends:
  - filename: hello.bst
    junction: hello-junction.bst
