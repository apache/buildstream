kind: manual

depends:
- filename: base.bst
  type: build

config:
  install-commands:
    - |
      python3 -c '
      from os.path import join
      from sys import argv
      from socket import socket, AF_UNIX, SOCK_STREAM
      s = socket(AF_UNIX, SOCK_STREAM)
      s.bind(join(argv[1], "testsocket"))
      ' %{install-root}
