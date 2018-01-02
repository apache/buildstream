kind: import
description: |

  This is the regular file staged twice, second time we stage into a subdir
  of the staging area. The subdir we specify is the file we already staged,
  provoking a plausible error where the user tries to stage something
  unreasonable.

sources:
- kind: local
  path: files/file.txt
- kind: local
  path: files/file.txt
  directory: file.txt
