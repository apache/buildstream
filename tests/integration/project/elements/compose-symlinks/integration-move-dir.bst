kind: stack

depends:
- filename: base.bst

public:
  bst:
    integration-commands:
    - |
      mkdir test
      mv foo test/
      mv bar test/
      ln -s /test/foo /foo
      ln -s /test/bar /bar
