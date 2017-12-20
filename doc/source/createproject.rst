.. _createproject:

Creating a basic project
====

This Section assumes you have installed Buildstream already.

If not, go to :ref:`installing`

Or :ref:`docker`

This section will be using files from Cmake-test 


Setup
----

If using docker, run::

  bst-here 

In the directory you want to use.

----

Create File Structure
~~~~

Create a project directory and in it create the following directories:

* elements

* elements/dependencies

* keys

* src




Source files
~~~~

There are multiple ways of including source files with buildstream, and this is done through things called plugins.

The list of options can be found here :ref:`plugins_sources`

Each option can be clicked for an example of an "element"


If you plan on following along with this tutorial, do the following:

    For this example we will be using cmake-test, as it is a relatively small and simple project to build.

    Download :download:`step7.tar.gz <../../integration-tests/cmake-test/src/step7.tar.gz>`

    This should provide you with `step7.tar.gz`

    Move `step7.tar.gz` to `src`

This file is the project repository, 

You can include repositories into buildstream in multiple ways.

One of which, is via a local tar.gz

Read :ref:`format_sources` for more information on the different options


    Download :download:`gnome-sdk.gpg <../../integration-tests/cmake-test/keys/gnome-sdk.gpg>`

    This should provide you with `gnome-sdk.gpg`

    Move `gnome-sdk.gpg` to `keys`

This key is needed in order to decrypt the files used in this example.

----

Creating the project files
----

Project.conf
~~~~

In the root of the project directory create a file called project.conf containing::

    name: ProjectName  # The name you want to give to your project
    element-path: elements # The relative path to the "elements" directory
    # The elements directory is where your .bst files will be stored
    aliases:
      name: url # This is used so you can moderate the URLs/Repos used by your build.
                # This way, they can be modified in a single place instead of multiple
                # Use this name in place of the url anywhere you would use it
      gnomesdk: https://sdk.gnome.org/

    options:
       arch:
         type: arch
         description: The machine architecture
         values:
         - x86_64
         - i386


step7.bst
~~~~

This is the element that is actually being called and build.
It depends on:
* usermerge.bst 
* base-sdk.bst



In the elements directory Create a file called step7.bst containing::

  kind: cmake # This is a build element plugin (linked below)
  description: Cmake test
  
  depends:
    - filename: dependencies/usermerge.bst
      type: build
    - filename: dependencies/base-sdk.bst
      type: build
  
  sources:
    - kind: tar # This is a Source Plugin
      url: [PathToProjectDir]/src/step7.tar.gz
  
:ref:`kind (plugins)<plugins_build>`

:ref:`format_depends`

:ref:`format_sources`

.. this is done until i can find a better way of incorperating hyperlinks into sourcecode blocks

base-sdk.bst
~~~~

In the elements/dependencies directory Create a file called base-sdk.bst containing::

 kind: import
 description: Import the base freedesktop SDK
 sources:
  - kind: ostree
    url: gnomesdk:repo/
    gpg-key: keys/gnome-sdk.gpg
    track: runtime/org.freedesktop.BaseSdk/x86_64/1.4
    ref: 0d9d255d56b08aeaaffb1c820eef85266eb730cb5667e50681185ccf5cd7c882
  config:
    source: files
    target: usr
 

:ref:`format_config`

usermerge.bst
~~~~

In the elements/dependencies directory Create a file called base-platform.bst containing::

  kind: import
  description: Some symlinks for the flatpak runtime environment
  sources:
    - kind: local
      path: files/usrmerge
