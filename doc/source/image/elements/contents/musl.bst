# elements/contents/musl.bst

kind: autotools

sources:
- kind: tar
  url: https://www.musl-libc.org/releases/musl-1.1.18.tar.gz

  ref: d017ee5d01aec0c522a1330fdff06b1e428cb409e1db819cc4935d5da4a5a118
depends:
- filename: base.bst
  type: build

config:
  configure-commands:
  - '%{configure}'
