# elements/image/initramfs/initramfs-gz.bst

kind: script
description: The compressed initramfs

depends:
- filename: image/initramfs/initramfs.bst
  type: build
- filename: contents.bst
  type: build

variables:
  cwd: "%{build-root}"

config:
  layout:
  - element: contents.bst
    destination: /
  - element: image/initramfs/initramfs.bst
    destination: "%{build-root}"

  commands:
  - mkdir -p %{install-root}/boot
  # We need to ensure exec permissions here.
  # See: https://gitlab.com/BuildStream/buildstream/issues/84
  - chmod +x ./sbin/init ./sbin/shutdown
  - (find . -print0 | cpio -0 -H newc -o) |
    gzip -c > %{install-root}/boot/initramfs.gz
