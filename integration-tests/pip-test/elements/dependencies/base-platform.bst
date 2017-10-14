kind: import
description: Import the base freedesktop platform
config:
  source: files
public:
  bst:
    integration-commands:
    - ldconfig
arches:
  x86_64:
    sources:
    - kind: ostree
      url: gnomesdk:repo/
      track: runtime/org.freedesktop.BasePlatform/x86_64/1.6
      gpg-key: keys/gnome-sdk.gpg
      ref: 9a2d4d9b4a2cf4e1ddcfd1b696e5cefba35d62b70ef61435b15ea3cb905cc4cf
  i386:
    sources:
    - kind: ostree
      url: gnomesdk:repo/
      track: runtime/org.freedesktop.BasePlatform/i386/1.6
      gpg-key: keys/gnome-sdk.gpg
