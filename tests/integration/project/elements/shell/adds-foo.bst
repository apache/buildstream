kind: manual
depends:
- base.bst

config:
  install-commands:
  - |
    install -D -m775 /proc/self/fd/0 %{install-root}%{bindir}/foo <<\EOF
    #!/bin/sh
    echo foo
    EOF
