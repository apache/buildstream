kind: autotools
description: |

    Hello world example from automake

variables:

  # The hello world example lives in the doc/amhello folder.
  #
  # Set the %{command-subdir} variable to that location
  # and just have the autotools element run its commands there.
  #
  command-subdir: doc/amhello

sources:
- kind: tar
  url: gnu:automake-1.16.1.tar.gz
  ref: 608a97523f97db32f1f5d5615c98ca69326ced2054c9f82e65bade7fc4c9dea8

depends:
- base.bst
