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
      track: runtime/org.freedesktop.BasePlatform/x86_64/1.4
      gpg-key: keys/gnome-sdk.gpg
      ref: c9d09b7250a12ef09d95952fc4f49a35e5f8c2c1dd7141b7eeada4069e6f6576
  i386:
    sources:
    - kind: ostree
      url: gnomesdk:repo/
      track: runtime/org.freedesktop.BasePlatform/i386/1.4
      gpg-key: keys/gnome-sdk.gpg
      ref: 27ebae91839a454596a273391b0e53063eaa8aca4fc9cb64654582bfbc338c96
