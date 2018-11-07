kind: compose

depends:
- fileNAME: import-dev.bst
  type: build

config:
  # Dont try running the sandbox, we dont have a
  # runtime to run anything in this context.
  integrate: False
