# elements/contents/busybox.bst

kind: manual

sources:
- kind: tar
  url: busybox:busybox-1.27.2.tar.bz2
depends:
- filename: base.bst
  type: build
- filename: contents/musl.bst
  type: runtime

environment:
  PATH: /usr/bin:/bin:/usr/sbin:/sbin:/tools/bin:/tools/sbin

config:
  configure-commands:
  # Busybox's default config has everything enabled.
  - make defconfig KCONFIG_NOTIMESTAMP=1

  # None of this is needed because we have kmod; and it actually breaks the
  # Linux build because depmod isn't compatible enough with util-linux's.
  - sed -e 's/CONFIG_DEPMOD=y.*/# CONFIG_DEPMOD is not set/' -i .config
  - sed -e 's/CONFIG_INSMOD=y.*/# CONFIG_INSMOD is not set/' -i .config
  - sed -e 's/CONFIG_MODPROBE=y.*/# CONFIG_MODPROBE is not set/' -i .config
  - sed -e 's/CONFIG_MODPROBE_SMALL=y.*/# CONFIG_MODPROBE_SMALL is not set/' -i .config
  - sed -e 's/CONFIG_LSMOD=y.*/# CONFIG_LSMOD is not set/' -i .config
  - sed -e 's/CONFIG_RMMOD=y.*/# CONFIG_RMMOD is not set/' -i .config

  build-commands:
  - make KCONFIG_NOTIMESTAMP=1

  install-commands:
  - |
    # Note here we intentionally ignore '%{prefix}', this is going into '/'
    make CONFIG_PREFIX="%{install-root}" KCONFIG_NOTIMESTAMP=1 install &&
    chmod 6755 "%{install-root}/bin/busybox"

  # We need to prepare the system for creating files in /etc later
  # (/etc/fstab, for example)
  - mkdir -p "%{install-root}/etc"

public:
  bst:
    split-rules:
      runtime:
        (>):
        - |
          /bin/*
        - |
          /sbin/*
