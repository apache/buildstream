kind: autotools
variables:
  result: "Nothing"
  (?):
  - machine_arch == "arm":
      result: "Army"
  - machine_arch == "aarch64":
      result: "Aarchy"
