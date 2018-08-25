

.. _install_linux_distro:

Installing from distro packages
===============================
BuildStream is available on some linux distributions, here are
some install instructions for the linux distributions which
have packaged BuildStream.


Arch Linux
----------
Packages for Arch exist in `AUR <https://wiki.archlinux.org/index.php/Arch_User_Repository#Installing_packages>`_.
Two different package versions are available:

* Latest release: `buildstream <https://aur.archlinux.org/packages/buildstream>`_
* Latest development snapshot: `buildstream-git <https://aur.archlinux.org/packages/buildstream-git>`_


Fedora
------
BuildStream is not yet in the official Fedora repositories, but you can
install it from a Copr::

  sudo dnf copr enable bochecha/buildstream
  sudo dnf install buildstream

Optionally, install the ``buildstream-docs`` package to have the BuildStream
documentation in Devhelp or GNOME Builder.
