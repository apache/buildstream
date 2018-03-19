# Optionally track the test branch
#
kind: import

sources:
- kind: git
  url: file://{repo}
  (?):
  - test:
      track: test
  - not test:
      track: master
