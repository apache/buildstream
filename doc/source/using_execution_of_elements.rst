Execution of BuildStream Elements
=================================

This page provides a guide on how Buildstream elements are built, including how
element types may affect this.

When a BuildStream element is being built, it can roughly be broken down
into these individual stages:

- Sources are fetched
- The sandbox is prepared
- Configure and run commands
- Caching Artifacts

Sources are fetched
-------------------

The hidden first step is actually validating the ``yaml``. This includes
resolving includes, options, appends, which are denoted by ``(@)``,
``(?)`` and ``(>)`` respectively.

The first step once the ``yaml`` has been validated is that BuildStream
will fetch the sources. This is dependent on the source ``kind`` as to
how these are fetched. After the sources are fetched they may need to
checked. For example a ``kind: tar`` would need to check the ``sha256``
matches, and a ``git_repo`` source would need to switch to the specified
commit sha.

The Sandbox is prepared
-----------------------

The Sandbox is prepared as a temporary filesystem, where build dependencies
(``build-depends:``), are staged, along with their own runtime dependencies.
This happens in an abstract state, which can quickly spot repeated files and
overlaps.

In general when a dependency is being staged, the produced artifact is
added from the root (``/``). This can sometimes be changed using the
``location:`` attribute. In most cases dependencies are marked by
BuildStream as immutable.

After the dependencies are staged BuildStream stages the sources in the
``build-root`` location. The actual location of this differs slightly
depending on the project file structure, which is why it is common to
see elements use the variable ``%{build-root}`` which resolves to the
correct location.

Configure and Build commands
----------------------------

Now that all dependencies and sources are staged in a temporary
filesystem, this filesystem is started up by BuildBox in a sandbox.

The first commands to be run are configure commands and it is
recommended to include things like moving the sources about, generating
config files and other “configure” related actions into this section.
These should be the commands that can only be run once (for example a
folder can only be moved once), this is due to `BuildStream
workspaces `<developing/workspaces.rst>`__.

!!! tip “BuildStream Workspaces and Configure Commands”

::

   When a [workspace](developing/workspaces.rst)
   is opened, it stages all the sources for the indicated element locally, then
   when doing a build of that element it uses these local sources instead of
   pulling in fresh sources. Builds using workspaces only run configure
   commands once, and any subsequent builds using the same workspace will skip
   the configure commands step, therefore steps of the build that aren't 
   repeatable (without re-staging sources) should be added to configure 
   commands.

After Configure commands are run, then Build commands are next. Build
commands are intended to contain the actual build process, for example
if the build uses ``make`` then this stage should run the
``make target`` command.

Install Commands and Caching Artifacts
--------------------------------------

Install commands are the final commands that are run before BuildStream
collects the artifacts and closes the build sandbox. Install commands
should mainly be comprised of moving the built artifacts from the
``${build-root}`` to the ``${install-root}``.

There is no need for Install commands to clean up any of the sources
that aren’t going to moved, as the BuildStream handles this when the
sandbox is closed.

Directories can be created under the install location, for example
``%{install-root}/example/``, and these will be maintained when another
element depends on this one, for example this will become
``/example``.

The contents of the install root are cached. BuildStream caches the
produced artifact to reduce the need to rebuild elements, instead it can
pull from this artifact cache. It will only rebuild an element if the
element file changes, or if the dependencies for an element changes.

!!! tip “Caching Errors”

::

   BuildStream will also cache build errors, and if no file has changed
   (including the dependencies) then BuildStream will display this cached error,
   without attempting a rebuild. This is sometimes not the desired behaviour,
   especially if the error was caused by a remote issue, like a source site
   being temporarily unavailable. To force an attempted build use the
   `-r`/`--retry-failed` option, documented
   [here](using_commands.rst#cmdoption-bst-build-r)
