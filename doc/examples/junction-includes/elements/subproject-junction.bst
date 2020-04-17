kind: junction

config:
  # Configure the options for subproject
  #
  # If our project is funky, then it requires
  # a blue subproject, otherwise we use a red one.
  #
  options:
    color: red
    (?):
    - funky == True:
        color: blue

sources:
- kind: local
  path: subproject
