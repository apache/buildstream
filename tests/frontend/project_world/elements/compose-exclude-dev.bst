kind: compose

depends:
- filename: import-bin.bst
  type: build
- filename: import-dev.bst
  type: build

config:
  # Dont try running the sandbox, we dont have a
  # runtime to run anything in this context.
  integrate: False

  # Exclude the dev domain
  exclude:
  - devel
