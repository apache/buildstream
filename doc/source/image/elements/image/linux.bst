# elements/image/linux.bst

kind: manual

depends:
- filename: base.bst
  type: build

sources:
- kind: tar
  url: kernel:linux/kernel/v4.x/linux-4.14.3.tar.xz
  ref: b628134ebb63ec82cb3e304a10aab2fd306fe79212e75ce81d8af73463c80366
config:
  configure-commands:
  - sed -i 's|#!/bin/bash|#!/bin/ash|' scripts/config
  - make defconfig
  - scripts/config -e PACKET
  - scripts/config -e SATA_AHCI
  - scripts/config -e ATA_GENERIC
  - scripts/config -e HAVE_IDE
  - scripts/config -d BLK_DEV_IDE_SATA
  - scripts/config -e BTRFS_FS
  - scripts/config -e BTRFS_FS_POSIX_ACL
  - scripts/config -e DEVTMPFS
  - scripts/config -e DEVTMPFS_MOUNT
  - scripts/config -e CONFIG_FHANDLE
  - scripts/config -e DEVPTS_MULTIPLE_INSTANCES
  - scripts/config -e CGROUPS
  - scripts/config -e AUTOFS4_FS
  - scripts/config --set-str UEVENT_HELPER_PATH ''
  - scripts/config -e EXT2_FS
  - scripts/config -e EXT2_FS_XATTR
  - scripts/config -e EXT2_FS_POSIX_ACL
  - scripts/config -e EXT2_FS_SECURITY
  - scripts/config -e EXT2_FS_XIP
  - scripts/config -e EXT3_FS
  - scripts/config -d EXT3_DEFAULTS_TO_ORDERED
  - scripts/config -e EXT3_FS_XATTR
  - scripts/config -e EXT3_FS_POSIX_ACL
  - scripts/config -e EXT3_FS_SECURITY
  - scripts/config -e EXT4_FS
  - scripts/config -e EXT4_FS_XATTR
  - scripts/config -e EXT4_FS_POSIX_ACL
  - scripts/config -e EXT4_FS_SECURITY
  - scripts/config -d EXT4_DEBUG
  - scripts/config -e FUSE_FS
  - scripts/config -e OVERLAY_FS
  - scripts/config -e XFS_FS
  - scripts/config -e LIBCRC32C
  - scripts/config -d JBD_DEBUG
  - scripts/config -d JBD2_DEBUG
  - scripts/config -e BLK_DEV_LOOP
  - scripts/config -d BLK_DEV_CRYPTOLOOP
  - scripts/config -e CEPH_FS
  - scripts/config --set-val BLK_DEV_LOOP_MIN_COUNT 8
  - scripts/config -e DM_SNAPSHOT
  - scripts/config -e VIRTIO
  - scripts/config -e VIRTIO_RING
  - scripts/config -e VIRTIO_PCI
  - scripts/config -e VIRTIO_BALLOON
  - scripts/config -e VIRTIO_BLK
  - scripts/config -e VIRTIO_NET
  - scripts/config -e VIRTIO_CONSOLE
  - scripts/config -e HW_RANDOM_VIRTIO
  - scripts/config -e 9P_FS
  - scripts/config -e 9P_FSCACHE
  - scripts/config -e 9P_FS_POSIX_ACL
  - scripts/config -e NET_9P
  - scripts/config -e NET_9P_VIRTIO
  - scripts/config -e R8169
  - scripts/config -e 8139TOO
  - scripts/config -e 8139CP
  - scripts/config -e ATL1
  - scripts/config -e ATL1C
  - scripts/config -e ATL1E
  - scripts/config -e E100
  - scripts/config -e E1000
  - scripts/config -e E1000E
  - scripts/config -e USB_USBNET
  - scripts/config -e USB_NET_AX8817X
  - scripts/config -e USB_NET_AX88179_178A
  - scripts/config -e USB_NET_DM9601
  - scripts/config -e IKCONFIG
  - scripts/config -e IKCONFIG_PROC
  - scripts/config -e SECCOMP
  - scripts/config -d DEBUG_STACK_TRACE
  - scripts/config -e NFSD
  - scripts/config -e NFSD_V3
  - scripts/config -e KVM
  - scripts/config -e TUN
  - scripts/config -e BRIDGE
  - scripts/config -e VHOST_NET
  - scripts/config -e NF_NAT
  - scripts/config -e IP_NF_NAT
  - scripts/config -e IP_NF_TARGET_MASQUERADE
  - scripts/config -e FB_VESA
  - scripts/config -e HOTPLUG_PCI
  - scripts/config -e HOTPLUG_PCI_ACPI
  - scripts/config -e VLAN_8021Q
  - scripts/config -e BRIDGE_VLAN_FILTERING
  - scripts/config -e BLK_DEV_NBD
  - scripts/config -e BRIDGE_NF_EBTABLES
  - scripts/config -e NETFILTER
  - scripts/config -e NETFILTER_ADVANCED
  - scripts/config -e NETFILTER_XT_MATCH_ADDRTYPE
  - scripts/config -e OPENVSWITCH
  - scripts/config -e OPENVSWITCH_VXLAN
  - scripts/config -e CONFIG_OPENVSWITCH_GRE
  - scripts/config -e NET_CLS_BASIC
  - scripts/config -e NET_SCH_INGRESS
  - scripts/config -e NET_ACT_POLICE
  - scripts/config -e NET_IPGRE_DEMUX
  - scripts/config -e NET_SCH_HTB
  - scripts/config -e NET_SCH_HFSC
  - scripts/config -e VXLAN
  - scripts/config -e VETH
  - scripts/config -e IP_NF_MATCH_AH
  - scripts/config -e IP_NF_MATCH_ECN
  - scripts/config -e IP_NF_MATCH_RPFILTER
  - scripts/config -e IP_NF_MATCH_TTL
  - scripts/config -e IP_NF_TARGET_SYNPROXY
  - scripts/config -e IP_NF_TARGET_NETMAP
  - scripts/config -e IP_NF_TARGET_REDIRECT
  - scripts/config -e IP_NF_TARGET_CLUSTERIP
  - scripts/config -e IP_NF_TARGET_ECN
  - scripts/config -e IP_NF_TARGET_TTL
  - scripts/config -e IP_NF_RAW
  - scripts/config -e IP_NF_SECURITY
  - scripts/config -e IP_NF_ARPTABLES
  - scripts/config -e KVM_INTEL
  - scripts/config -e NETFILTER_NETLINK_QUEUE
  - scripts/config -e SCSI_NETLINK
  - scripts/config -e NETFILTER_XT_TARGET_MARK
  - scripts/config -e NETFILTER_XT_SET
  - scripts/config -e IP_SET
  - scripts/config -e IP_SET_BITMAP_IP
  - scripts/config -e IP_SET_BITMAP_IPMAC
  - scripts/config -e IP_SET_BITMAP_PORT
  - scripts/config -e IP_SET_HASH_IP
  - scripts/config -e IP_SET_HASH_IPMARK
  - scripts/config -e IP_SET_HASH_IPPORT
  - scripts/config -e IP_SET_HASH_IPPORTIP
  - scripts/config -e IP_SET_HASH_IPPORTNET
  - scripts/config -e IP_SET_HASH_MAC
  - scripts/config -e IP_SET_HASH_NETPORTNET
  - scripts/config -e IP_SET_HASH_NET
  - scripts/config -e IP_SET_HASH_NETNET
  - scripts/config -e IP_SET_HASH_NETPORT
  - scripts/config -e IP_SET_HASH_NETIFACE
  - scripts/config -e IP_SET_LIST_SET
  - scripts/config -e NF_CONNTRACK_TIMEOUT
  - scripts/config -e NF_CONNTRACK_TIMESTAMP
  - scripts/config -e NF_CONNTRACK_EVENTS
  - scripts/config -e NF_CONNTRACK_LABELS
  - scripts/config -e NETFILTER_NETLINK_ACCT
  - scripts/config -e NETFILTER_NETLINK_QUEUE_CT
  - scripts/config -e NF_CT_PROTO_DCCP
  - scripts/config -e NF_CT_PROTO_GRE
  - scripts/config -e NF_CT_PROTO_SCTP
  - scripts/config -e NF_CT_PROTO_UDPLITE
  - scripts/config -e NF_CT_NETLINK_TIMEOUT
  - scripts/config -e NF_CT_NETLINK_HELPER
  - scripts/config -e NF_CONNTRACK_AMANDA
  - scripts/config -e NF_CONNTRACK_H323
  - scripts/config -e NF_CONNTRACK_BROADCAST
  - scripts/config -e NF_CONNTRACK_NETBIOS_NS
  - scripts/config -e NF_CONNTRACK_SNMP
  - scripts/config -e NF_CONNTRACK_PPTP
  - scripts/config -e NF_CONNTRACK_SANE
  - scripts/config -e NF_CONNTRACK_TFTP
  - scripts/config -e NF_LOG_COMMON
  - scripts/config -e NF_NAT_PROTO_DCCP
  - scripts/config -e NF_NAT_PROTO_UDPLITE
  - scripts/config -e NF_NAT_PROTO_SCTP
  - scripts/config -e NF_NAT_AMANDA
  - scripts/config -e NF_NAT_TFTP
  - scripts/config -e NF_TABLES
  - scripts/config -e NF_TABLES_INET
  - scripts/config -e NFT_COMPAT
  - scripts/config -e NFT_EXTHDR
  - scripts/config -e NFT_META
  - scripts/config -e NFT_CT
  - scripts/config -e NFT_LIMIT
  - scripts/config -e NFT_NAT
  - scripts/config -e NFT_QUEUE
  - scripts/config -e NFT_REJECT
  - scripts/config -e NFT_REJECT_INET
  - scripts/config -e NFT_RBTREE
  - scripts/config -e NFT_HASH
  - scripts/config -e NFT_COUNTER
  - scripts/config -e NFT_LOG
  - scripts/config -e NFT_MASQ
  - scripts/config -e NETFILTER_XT_CONNMARK
  - scripts/config -e NETFILTER_XT_TARGET_AUDIT
  - scripts/config -e NETFILTER_XT_TARGET_CHECKSUM
  - scripts/config -e NETFILTER_XT_TARGET_CLASSIFY
  - scripts/config -e NETFILTER_XT_TARGET_CT
  - scripts/config -e NETFILTER_XT_TARGET_DSCP
  - scripts/config -e NETFILTER_XT_TARGET_HMARK
  - scripts/config -e NETFILTER_XT_TARGET_LED
  - scripts/config -e NETFILTER_XT_TARGET_LOG
  - scripts/config -e NETFILTER_XT_TARGET_NFQUEUE
  - scripts/config -e NETFILTER_XT_TARGET_RATEEST
  - scripts/config -e NETFILTER_XT_TARGET_TPROXY
  - scripts/config -e NETFILTER_XT_TARGET_TCPOPTSTRIP
  - scripts/config -e NETFILTER_XT_TARGET_TEE
  - scripts/config -e NETFILTER_XT_TARGET_TRACE
  - scripts/config -e NETFILTER_XT_TARGET_IDLETIMER
  - scripts/config -e NETFILTER_XT_MATCH_BPF
  - scripts/config -e NETFILTER_XT_MATCH_CLUSTER
  - scripts/config -e NETFILTER_XT_MATCH_COMMENT
  - scripts/config -e NETFILTER_XT_MATCH_CONNBYTES
  - scripts/config -e NETFILTER_XT_MATCH_CONNLABEL
  - scripts/config -e NETFILTER_XT_MATCH_CONNLIMIT
  - scripts/config -e NETFILTER_XT_MATCH_CPU
  - scripts/config -e NETFILTER_XT_MATCH_DCCP
  - scripts/config -e NETFILTER_XT_MATCH_DEVGROUP
  - scripts/config -e NETFILTER_XT_MATCH_DSCP
  - scripts/config -e NETFILTER_XT_MATCH_ESP
  - scripts/config -e NETFILTER_XT_MATCH_HASHLIMIT
  - scripts/config -e NETFILTER_XT_MATCH_HELPER
  - scripts/config -e NETFILTER_XT_MATCH_IPCOMP
  - scripts/config -e NETFILTER_XT_MATCH_IPRANGE
  - scripts/config -e NETFILTER_XT_MATCH_IPVS
  - scripts/config -e NETFILTER_XT_MATCH_L2TP
  - scripts/config -e NETFILTER_XT_MATCH_LENGTH
  - scripts/config -e NETFILTER_XT_MATCH_LIMIT
  - scripts/config -e NETFILTER_XT_MATCH_MAC
  - scripts/config -e NETFILTER_XT_MATCH_MULTIPORT
  - scripts/config -e NETFILTER_XT_MATCH_NFACCT
  - scripts/config -e NETFILTER_XT_MATCH_OSF
  - scripts/config -e NETFILTER_XT_MATCH_OWNER
  - scripts/config -e NETFILTER_XT_MATCH_CGROUP
  - scripts/config -e NETFILTER_XT_MATCH_PHYSDEV
  - scripts/config -e NETFILTER_XT_MATCH_PKTTYPE
  - scripts/config -e NETFILTER_XT_MATCH_QUOTA
  - scripts/config -e NETFILTER_XT_MATCH_RATEEST
  - scripts/config -e NETFILTER_XT_MATCH_REALM
  - scripts/config -e NETFILTER_XT_MATCH_RECENT
  - scripts/config -e NETFILTER_XT_MATCH_SCTP
  - scripts/config -e NETFILTER_XT_MATCH_SOCKET
  - scripts/config -e NETFILTER_XT_MATCH_STATISTIC
  - scripts/config -e NETFILTER_XT_MATCH_STRING
  - scripts/config -e NETFILTER_XT_MATCH_TCPMSS
  - scripts/config -e NETFILTER_XT_MATCH_TIME
  - scripts/config -e NETFILTER_XT_MATCH_U32
  - scripts/config -e IP_VS
  - scripts/config -e BRIDGE_NETFILTER
  - scripts/config -e CRYPTO_CRC32C
  - scripts/config -e CONFIGFS_FS
  - scripts/config -e EXPERT
  - scripts/config -e TARGET_CORE
  - scripts/config -e ISCSI_TARGET
  - scripts/config -e TCM_IBLOCK
  - scripts/config -e TCM_FILEIO
  - scripts/config -e TCM_PSCSI
  - scripts/config -e TCM_USER
  - scripts/config -e CONFIG_UIO
  - scripts/config -e LOOPBACK_TARGET
  - scripts/config -e TCM_FC
  - scripts/config -e LIBFC
  - scripts/config -e SCSI_FC_ATTRS
  - scripts/config -e SCSI_ISCSI_ATTRS
  - scripts/config -e ISCSI_TCP
  - scripts/config -e SCSI_LOWLEVEL
  - scripts/config -e SCSI_VIRTIO
  - scripts/config -e HYPERVISOR_GUEST
  - scripts/config -e PARAVIRT
  - scripts/config -e CONFIG_SND_INTEL8X0
  - scripts/config -m CONFIG_DRM_CIRRUS_QEMU
  - scripts/config -m CONFIG_DRM_BOCHS
  - scripts/config -m CONFIG_DRM_VIRTIO_GPU
  - scripts/config -e BT
  - yes '' | make oldconfig
  build-commands:
  - make $MAKEFLAGS
  install-commands:
  - mkdir -p "%{install-root}"/boot
  - make INSTALL_PATH="%{install-root}"/boot install
  - make INSTALL_MOD_PATH="%{install-root}" modules_install
  - install -d "%{install-root}%{prefix}/src/linux"
  - |
    (
        printf 'Makefile\0'
        printf 'Module.symvers\0'
        find arch/x86 -maxdepth 1 -name 'Makefile*' -print0
        find arch/x86 \( -name 'module.lds' -o -name 'Kbuild.platforms' -o -name 'Platform' \) -print0
        find arch/x86 \( -type d -a \( -name include -o -name scripts \) \) -o \
                                 \! -type d -a \( -path '*include/*' -o -path '*scripts/*' \) -print0
        find include -name 'asm*' -prune -o -print0
        find include/asm-generic -print0
        find include/uapi -print0
        find scripts -print0
    ) | cpio -0pumd "%{install-root}%{prefix}/src/linux"
public:
  bst:
    integration-commands:
    - if which depmod; then (cd /usr/lib/modules && for version in *; do depmod -a
      "$version"; done) fi
