# elements/image-x86_64.bst

# Specify the plugin reference - we want to import the x86image plugin
# from buildstream-external
kind: x86image
description: Create a deployment of a Linux system
depends:
  - filename: image/system.bst
    type: build
  - filename: base.bst
    type: build

# Boot image settings; the defaults can work, but you almost certainly
# want to customize them to match your image requirements.
#
# These settings are tailored to this specific project, don't just
# blindly copy.
variables:
  # Size of the disk to create
  #
  # Should be able to calculate this based on the space
  # used, however it must be a multiple of (63 * 512) bytes
  # as mtools wants a size that is divisible by sectors (512 bytes)
  # per track (63).
  boot-size: 16M
  rootfs-size: 69M
  sector-size: 512
  swap-size: 40K
  kernel-args: root=/dev/sda2 rootfstype=ext4 init=/sbin/init console=ttyS0
  kernel-name: vmlinuz-4.14.3

config:
  # The element that should be staged into "/". It must contain
  # all the tools required to generate the image
  base: base.bst

  # The element that should be staged into %{build-root}. It is expected
  # to be the system that you're planning to turn into an image.
  input: image/system.bst

  # This is technically not necessary, but convenient for trying
  # things out :)
  final-commands:
    (>):
    - |
      cat > %{install-root}/run-in-qemu.sh << EOF
      #!/bin/sh
      qemu-system-x86_64 -drive file=sda.img,format=raw -nographic
      EOF
      chmod +x %{install-root}/run-in-qemu.sh
