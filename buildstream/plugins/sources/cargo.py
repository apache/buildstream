#
#  Copyright (C) 2018 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Valentin David  <valentin.david@codethink.co.uk>

"""
cargo - stage files from cargo manifest
=======================================

`cargo` downloads and stages cargo crates based on a `Cargo.toml`
manifest provided by a previous source.

`ref` will contain the `Cargo.lock` file. `bst track` should be used
to set it.

When `keep-lock` is true, tracking will store the current `Cargo.lock`
provided by previous sources. in the `ref`. If `keep-lock` is false or
absent, then `ref` will be created for the latest available crates.

**Host dependencies:**

  * cargo
  * cargo-vendor (can be installed with `cargo install cargo-vendor`).

**Usage:**

.. code:: yaml

   # Specify the cargo source kind
   kind: cargo

   # Optionally give the subdirectory where the `Cargo.toml` manifest
   # can be found.
   subdir: subproject

   # Optionally disallow rewriting `Cargo.lock`. In this case tracking
   # will just read the existing file. If not used, then tracking
   # will create `Cargo.lock`.
   keep-lock: true
"""


import hashlib
import os
import errno

from buildstream import Consistency, Source, utils, SourceError


class CargoSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_REQUIRES_PREVIOUS_SOURCES_TRACK = True
    BST_REQUIRES_PREVIOUS_SOURCES_FETCH = True

    def configure(self, node):
        self.node_validate(node, ['ref', 'subdir', 'keep-lock'] + Source.COMMON_CONFIG_KEYS)
        self.ref = self.node_get_member(node, str, 'ref', None)
        self.subdir = self.node_get_member(node, str, 'subdir', '.')
        self.keeplock = self.node_get_member(node, bool, 'keep-lock', False)
        self.extra_path = None

    def preflight(self):
        self.host_cargo = utils.get_host_tool('cargo')

        try:
            utils.get_host_tool('cargo-vendor')
        except utils.ProgramNotFoundError:
            cargo_home = os.environ.get('CARGO_HOME', os.path.expanduser('~/.cargo'))
            self.extra_path = os.path.join(cargo_home, 'bin')

        self.call([self.host_cargo, 'vendor', '-V'],
                  env=self._environment(),
                  fail='Cannot find "cargo vendor". Please install it with "cargo install cargo-vendor".')

    def get_unique_key(self):
        return [self.subdir, self.ref]

    def get_ref(self):
        return self.ref

    def load_ref(self, node):
        self.ref = self.node_get_member(node, str, 'ref', None)

    def set_ref(self, ref, node):
        node['ref'] = self.ref = ref

    def _environment(self, *, set_home=False):
        env = {}
        env.update(os.environ)
        if self.extra_path:
            path = env.get('PATH', '').split(':')
            path.append(self.extra_path)
            env['PATH'] = ':'.join(path)
        if set_home:
            home = os.path.join(self.get_mirror_directory(), 'home')
            os.makedirs(home, exist_ok=True)
            env['CARGO_HOME'] = home
        return env

    def _get_manifest(self, directory):
        projectdir = os.path.join(directory, self.subdir)
        manifest = os.path.join(projectdir, 'Cargo.toml')
        lockfile = os.path.join(projectdir, 'Cargo.lock')
        return manifest, lockfile

    def track(self, previous_sources_dir):
        manifest, lockfile = self._get_manifest(previous_sources_dir)

        if not self.keeplock:
            self.call([self.host_cargo, 'generate-lockfile', '--manifest-path', manifest],
                      env=self._environment(set_home=True),
                      fail="Failed to track cargo packages")
        try:
            with open(lockfile, 'rb') as f:
                lockcontent = f.read().decode('utf-8')
        except OSError as e:
            if self.keeplock and e.errno == errno.ENOENT:
                raise SourceError("{}: Cannot find Cargo.lock".format(self))
            else:
                raise

        return lockcontent

    def _get_stamp(self):
        h = hashlib.sha256()
        h.update(self.get_ref().encode('utf-8'))
        return os.path.join(self.get_mirror_directory(), 'stamps', h.hexdigest())

    def get_consistency(self):
        if not self.ref:
            return Consistency.INCONSISTENT
        if os.path.exists(self._get_stamp()):
            return Consistency.CACHED
        return Consistency.RESOLVED

    def fetch(self, previous_sources_dir):
        manifest, lockfile = self._get_manifest(previous_sources_dir)
        if not self.keeplock:
            with open(lockfile, 'wb') as f:
                f.write(self.get_ref().encode('utf-8'))

        self.call([self.host_cargo, 'fetch', '--manifest-path', manifest, '--locked'],
                  env=self._environment(set_home=True),
                  fail="Failed to fetch cargo packages")
        stamp = self._get_stamp()
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        with open(stamp, 'w'):
            pass

    def stage(self, directory):
        manifest, lockfile = self._get_manifest(directory)
        if not self.keeplock:
            with open(lockfile, 'wb') as f:
                f.write(self.ref.encode('utf-8'))

        config = os.path.join(os.path.dirname(manifest), '.cargo', 'config')
        os.makedirs(os.path.dirname(config), exist_ok=True)

        vendordir = os.path.join(directory, 'vendor')
        relvendordir = os.path.relpath(vendordir, os.path.dirname(manifest))

        with utils.save_file_atomic(config, 'wb') as f:
            self.call([self.host_cargo, 'vendor', '--frozen', '--relative-path', relvendordir],
                      env=self._environment(set_home=True),
                      cwd=os.path.dirname(manifest),
                      stdout=f,
                      fail="Failed to stage cargo packages")


def setup():
    return CargoSource
