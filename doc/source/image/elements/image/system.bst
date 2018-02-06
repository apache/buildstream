# elements/image/system.bst

kind: compose
description: The system installed onto the image

depends:
  - filename: contents.bst
    type: build
  - filename: image/linux.bst
    type: build
  - filename: image/initramfs/initramfs-gz.bst
    type: build

config:
  include:
    - runtime
