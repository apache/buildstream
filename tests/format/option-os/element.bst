kind: manual
variables:
  result: "Nothing"
  (?):
  - machine_os == "Linux":
      result: "Linuxy"
  - machine_os == "Darwin":
      result: "Darwiny"
  - machine_os == "SunOS":
      result: "SunOSy"
  - machine_os == "FreeBSD":
      result: "FreeBSDy"