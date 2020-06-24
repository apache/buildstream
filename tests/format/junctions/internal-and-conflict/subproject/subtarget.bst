kind: compose

# Use a build dependency on our internal subsubproject target.
#
# There is currently no validation for this but it may be
# introduced in the future. For correctness of this test,
# use a build dependency.
#
build-depends:
- subsubproject.bst:target.bst
