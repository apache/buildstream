kind: junction
sources:
- kind: local
  path: base

#
# In this case, the "base" subproject does not really
# have a subproject to override, but we're using this
# setup to test the error of overriding a subproject
# with the junction declaring the override, which will
# happen sooner than noticing there is not a subproject.bst
# to override.
#
config:
  overrides:
    subproject.bst: subproject-self-override.bst
