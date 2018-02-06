# elements/image/initramfs/initramfs.bst

kind: compose
description: Initramfs composition

depends:
  - filename: contents.bst
    type: build
  - filename: image/initramfs/initramfs-scripts.bst
    type: build

config:
  include:
  - runtime
