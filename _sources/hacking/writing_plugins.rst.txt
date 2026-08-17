..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.



.. _writing_plugins:

Adding core plugins
-------------------
This is a checklist of things which need to be done when adding a new
core plugin to BuildStream proper.


Update documentation index
~~~~~~~~~~~~~~~~~~~~~~~~~~
The documentation generating scripts will automatically pick up your
newly added plugin and generate HTML, but will not add a link to the
documentation of your plugin automatically.

Whenever adding a new plugin, you must add an entry for it in ``doc/source/core_plugins.rst``.


Add tests
~~~~~~~~~
Needless to say, all new feature additions need to be tested. For ``Element``
plugins, these usually need to be added to the integration tests. For ``Source``
plugins, the tests are added in two ways:

* For most normal ``Source`` plugins, it is important to add a new ``Repo``
  implementation for your plugin in the ``tests/testutils/repo/`` directory
  and update ``ALL_REPO_KINDS`` in ``tests/testutils/repo/__init__.py``. This
  will include your new ``Source`` implementation in a series of already existing
  tests, ensuring it works well under normal operating conditions.

* For other source plugins, or in order to test edge cases, such as failure modes,
  which are not tested under the normal test battery, add new tests in ``tests/sources``.


Extend the cachekey test
~~~~~~~~~~~~~~~~~~~~~~~~
For any newly added plugins, it is important to add some new simple elements
in ``tests/cachekey/project/elements`` or ``tests/cachekey/project/sources``,
and ensure that the newly added elements are depended on by ``tests/cachekey/project/target.bst``.

One new element should be added to the cache key test for every configuration
value which your plugin understands which can possibly affect the result of
your plugin's ``Plugin.get_unique_key()`` implementation.

This test ensures that cache keys do not unexpectedly change or become incompatible
due to code changes. As such, the cache key test should have full coverage of every
YAML configuration which can possibly affect cache key outcome at all times.

See the ``src/buildstream/testing/_update_cachekeys.py`` file for instructions on running the updater,
you need to run the updater to generate the ``.expected`` files and add the new
``.expected`` files in the same commit which extends the cache key test.
