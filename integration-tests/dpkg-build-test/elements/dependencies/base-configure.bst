kind: script
depends:
- filename: dependencies/base-system.bst
  type: build

variables:
  install-root: /

config:

  commands:
  - |
    # Avoid some chowns which fail at dpkg configure time
    #
    mv /bin/chown /bin/chown.real
    ln -s true /bin/chown

  - |
    # This is expected to fail, but will configure everything we need
    # at least for the purpose of building, other dpkg scripts which
    # require real root privileges will always fail here.
    DEBIAN_FRONTEND=noninteractive dpkg --configure -a --abort-after=100000 || exit 0

  - |
    # Restore chown
    #
    rm -f /bin/chown
    mv /bin/chown.real /bin/chown
