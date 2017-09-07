#!/usr/bin/env python3
#
#  Copyright (C) 2017 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""Dpkg deployment element

A :mod:`ScriptElement <buildstream.scriptelement>` implementation for creating
debian packages

Default Configuration
~~~~~~~~~~~~~~~~~~~~~

The dpkg_deploy default configuration:
  .. literalinclude:: ../../../buildstream/plugins/elements/dpkg_deploy.yaml
     :language: yaml

Public Data
~~~~~~~~~~~

This plugin uses the public data of the element indicated by `config.input`
to generate debian packages.

split-rules
-----------

This plugin consumes the input element's split-rules to identify which file
goes in which package, e.g.

.. code:: yaml

   public:
     split-rules:
       foo:
       - /sbin/foo
       - /usr/bin/bar
       bar:
       - /etc/quux

dpkg-data
---------

control
'''''''

The control field is used to generate the control file for each package, e.g.

.. code:: yaml

   public:
     dpkg-data:
       foo:
         control: |
           Source: foo
           Section: blah
           Build-depends: bar (>= 1337), baz
           ...

name
''''

If the "name" field is present, the generated package will use that field to
determine its name.
If "name" is not present, the generated package will be named
<element_name>-<package_name>

i.e. in an element named foo:

.. code:: yaml

   public:
     dpkg-data:
       bar:
         name: foobar

will be named "foobar", while the following data:

.. code:: yaml

   public:
     dpkg-data:
       bar:
         ...

will create a package named "foo-bar"

package-scripts
---------------

preinst, postinst, prerm and postrm scripts will be generated
based on data in pacakge-scripts, if it exists. The scripts are formatted as
raw text, e.g.

.. code:: yaml

   public:
     package-scripts:
       foo:
         preinst: |
           #!/usr/bin/bash
           /sbin/ldconfig
       bar:
         postinst: |
           #!/usr/bin/bash
           /usr/share/fonts/generate_fonts.sh

"""

import hashlib
import os
import re
from buildstream import ScriptElement, Scope, utils


def md5sum_file(path):
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# Element implementation for the 'dpkg_deploy' kind.
class DpkgDeployElement(ScriptElement):
    def configure(self, node):
        prefixes = ["pre-", "", "post-"]
        groups = ["build-commands"]

        self.node_validate(node, [
            'pre-build-commands', 'build-commands', 'post-build-commands',
            'base', 'input'
        ])

        self.__input = self.node_subst_member(node, 'input')
        self.layout_add(self.node_subst_member(node, 'base'), "/")
        self.layout_add(None, '/buildstream')
        self.layout_add(self.__input,
                        self.get_variable('build-root'))
        self.unedited_cmds = {}
        for group in groups:
            cmds = []
            if group not in node:
                raise ElementError("{}: Unexpectedly missing command group '{}'"
                                   .format(self, group))
            for prefix in prefixes:
                if prefix + group in node:
                    cmds += self.node_subst_list(node, prefix + group)
            self.unedited_cmds[group] = cmds

        self.set_work_dir()
        self.set_install_root()
        self.set_root_read_only(True)

    def get_unique_key(self):
        key = super().get_unique_key()
        del key["commands"]
        key["unedited-commands"] = self.unedited_cmds
        return key

    def stage(self, sandbox):
        super().stage(sandbox)
        # For each package, create a subdir in build-root and copy the files to there
        # then reconstitute the /DEBIAN files.
        input_elm = self.search(Scope.BUILD, self.__input)
        if not input_elm:
            self.error("{}: Failed to find input element {} in build-depends"
                       .format(self.name, self.__input))
            return
        bstdata = input_elm.get_public_data('bst')
        if "dpkg-data" not in bstdata:
            self.error("{}: input element {} does not have any bst.dpkg-data public data"
                       .format(self.name, self.__input))
        for package, package_data in self.node_items(bstdata['dpkg-data']):
            package_name = package_data.get("name", "{}-{}".format(input_elm.normal_name, package))
            if not ("split-rules" in bstdata and
                    package in bstdata["split-rules"]):
                self.error("{}: Input element {} does not have bst.split-rules.{}"
                           .format(self.name, self.__input.name, package))
            package_splits = bstdata['split-rules'][package]
            src = os.path.join(sandbox.get_directory(),
                               self.get_variable("build-root").lstrip(os.sep))
            dst = os.path.join(src, package)
            os.makedirs(dst, exist_ok=True)
            utils.link_files(src, dst, package_splits)

            # Create this dir. If it already exists,
            # something unexpected has happened.
            debiandir = os.path.join(dst, "DEBIAN")
            os.makedirs(debiandir)

            # Recreate the DEBIAN files.
            # control is extracted verbatim, and is mandatory.
            if "control" not in package_data:
                self.error("{}: Cannot reconstitute package {}".format(self.name, package),
                           detail="There is no public.bst.dpkg-data.{}.control".format(package))
            controlpath = os.path.join(debiandir, "control")
            controltext = package_data["control"]
            # Slightly ugly way of renaming the package
            controltext = re.sub(r"^Package:\s*\S+",
                                 "Package: {}".format(package_name),
                                 controltext)
            with open(controlpath, "w") as f:
                f.write(controltext)

            # Generate a DEBIAN/md5sums file from the artifact
            md5sums = {}
            for split in package_splits:
                filepath = os.path.join(src, split.lstrip(os.sep))
                if os.path.isfile(filepath):
                    md5sums[split] = md5sum_file(filepath)
            md5sumspath = os.path.join(debiandir, "md5sums")
            with open(md5sumspath, "w") as f:
                for path, md5sum in md5sums.items():
                    f.write("{}  {}\n".format(md5sum, path))

            # scripts may exist
            if ("package-scripts" in bstdata and
                    package in bstdata["package-scripts"]):
                for script in ["postinst", "preinst", "postrm", "prerm"]:
                    if script in bstdata["package-scripts"][package]:
                        filepath = os.path.join(debiandir, script)
                        with open(filepath, "w") as f:
                            f.write(bstdata["package-scripts"][package][script])
                        os.chmod(filepath, 0o755)

    def _packages_list(self):
        input_elm = self.search(Scope.BUILD, self.__input)
        if not input_elm:
            detail = ("Available elements are {}"
                      .format("\n".join([x.name for x in self.dependencies(Scope.BUILD)])))
            self.error("{} Failed to find element {}".format(self.name, self.__input),
                       detail=detail)

        bstdata = input_elm.get_public_data("bst")
        if "dpkg-data" not in bstdata:
            self.error("{}: Can't get package list for {}, no bst.dpkg-data"
                       .format(self.name, self.__input))
        return " ".join([k for k, v in self.node_items(bstdata["dpkg-data"])])

    def _sub_packages_list(self, cmdlist):
        return [
            cmd.replace("<PACKAGES>", self._packages_list()) for cmd in cmdlist
        ]

    def assemble(self, sandbox):
        # Mangle commands here to replace <PACKAGES> with the list of packages.
        # It can't be done in configure (where it was originally set) because
        # we don't have access to the input element at that time.
        for group, commands in self.unedited_cmds.items():
            self.add_commands(group, self._sub_packages_list(commands))
        return super().assemble(sandbox)


# Plugin entry point
def setup():
    return DpkgDeployElement
