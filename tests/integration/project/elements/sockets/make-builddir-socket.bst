kind: manual

depends:
- filename: base.bst
  type: build

config:
  build-commands:
    - |
      python3 -c '
      from socket import socket, AF_UNIX, SOCK_STREAM
      s = socket(AF_UNIX, SOCK_STREAM)
      s.bind("testsocket")
      '
