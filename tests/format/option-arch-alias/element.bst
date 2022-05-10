kind: manual
variables:
  result: "Nothing"
  (?):
  - machine_arch == "arm":
      result: "Army"
  - machine_arch == "x86_64":
      result: "X86-64y"
