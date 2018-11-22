kind: import
description: Import the base freedesktop SDK
sources:
- kind: ostree
  url: gnomesdk:repo/
  gpg-key: keys/gnome-sdk.gpg
  (?):
  - arch == "x86-64":
      track: runtime/org.freedesktop.BaseSdk/x86_64/1.4
      ref: 0d9d255d56b08aeaaffb1c820eef85266eb730cb5667e50681185ccf5cd7c882
  - arch == "x86-32":
      track: runtime/org.freedesktop.BaseSdk/i386/1.4
      ref: 16036b747c1ec8e7fe291f5b1f667cb942f0267d08fcad962e9b7627d6cf1981
config:
  source: files
  target: usr
