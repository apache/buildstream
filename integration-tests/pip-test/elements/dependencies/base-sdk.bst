kind: import
description: Import the base freedesktop SDK
sources:
- kind: ostree
  url: gnomesdk:repo/
  gpg-key: keys/gnome-sdk.gpg
  (?):
  - arch == "x86_64":
      track: runtime/org.freedesktop.BaseSdk/x86_64/1.6
      ref: fa0dbd1b1eee9ec89518c1938c89803e0c54a12cd7ce892082433ad56b8a6f9b
  - arch == "i386":
      track: runtime/org.freedesktop.BaseSdk/i386/1.6
config:
  source: files
  target: usr
