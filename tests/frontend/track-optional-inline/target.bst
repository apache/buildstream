# Optionally track the test branch
#
kind: import

(?):
- test:
    sources:
    - kind: git
      url: file://{repo}
      track: test
- not test:
    sources:
    - kind: git
      url: file://{repo}
      track: master
