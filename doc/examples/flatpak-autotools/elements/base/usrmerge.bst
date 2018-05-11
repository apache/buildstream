kind: import
description: Base usr merge symlinks

# Depend on the base-sdk.bst such that the
# symlinks get added after staging the SDK
depends:
- base/sdk.bst

sources:
- kind: local
  path: files/links
