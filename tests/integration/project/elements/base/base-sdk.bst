kind: import
description: Import the base freedesktop SDK
(?):
  - linux == True:
      sources:
        - kind: ostree
          url: gnomesdk:repo/
          gpg-key: keys/gnome-sdk.gpg
          track: runtime/org.freedesktop.BaseSdk/x86_64/1.6
          ref: 48b8c907522d3edeb0fb9f36c6515ce1ef5fb80a6e4e5dd54033b3fd6ad784d0
  - linux == False:
      sources:
        - kind: tar
          url: gnome7:tarballs/gnome-sdk.tar.xz
          ref: 96d5062a19fa9ac3439f8a502664f8d46860bad7efd28e7909b03ddbcdbe66e6
config:
  source: files
  target: usr
