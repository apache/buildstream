kind: import
description: Import the base freedesktop SDK
config:
  source: files
  target: usr
arches:
  x86_64:
    sources:
    - kind: ostree
      url: gnomesdk:repo/
      track: runtime/org.freedesktop.BaseSdk/x86_64/1.6
      gpg-key: keys/gnome-sdk.gpg
      ref: fa0dbd1b1eee9ec89518c1938c89803e0c54a12cd7ce892082433ad56b8a6f9b
  i386:
    sources:
    - kind: ostree
      url: gnomesdk:repo/
      track: runtime/org.freedesktop.BaseSdk/i386/1.6
      gpg-key: keys/gnome-sdk.gpg
