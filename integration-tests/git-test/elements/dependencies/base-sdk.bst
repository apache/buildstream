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
      track: runtime/org.freedesktop.BaseSdk/x86_64/1.4
      gpg-key: keys/gnome-sdk.gpg
      ref: 0d9d255d56b08aeaaffb1c820eef85266eb730cb5667e50681185ccf5cd7c882
  i386:
    sources:
    - kind: ostree
      url: gnomesdk:repo/
      track: runtime/org.freedesktop.BaseSdk/i386/1.4
      gpg-key: keys/gnome-sdk.gpg
      ref: 16036b747c1ec8e7fe291f5b1f667cb942f0267d08fcad962e9b7627d6cf1981
