# elements/contents/hello.bst

kind: import

sources:
  - kind: local
    path: files/hello
    directory: /usr/bin

depends:
  - filename: contents/busybox.bst
    type: runtime
