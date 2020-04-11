kind: autotools
description: |

    Hello world example from automake

variables:

  # The special paths.bst from our subproject is used to
  # define the paths of some elements in this project.
  #
  (@): subproject-junction.bst:include/paths.bst

  # The hello world example lives in the doc/amhello folder.
  command-subdir: doc/amhello

sources:
- kind: tar
  url: gnu:automake-1.16.tar.gz
  ref: 80da43bb5665596ee389e6d8b64b4f122ea4b92a685b1dbd813cd1f0e0c2d83f

depends:
  - filename: base.bst
    junction: subproject-junction.bst
