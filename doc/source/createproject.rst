.. _createproject:

Creating a basic project
====

This Section assumes you have installed Buildstream already.

If not, go to :ref:`installing`

Or :ref:`docker`

This section will be using files from: 

https://gitlab.com/BuildStream/buildstream/tree/master/integration-tests/cmake-test/

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

There are multiple ways of including source files with build stream, and this is done though things called plugins.

The list of options can be found here :ref:`plugins_sources`
And each option can be clicked for an example of "element"


If you plan on following along with this tutorial, do the following:

    Install wget or some other download tool.

    For this example we will be using cmake-test, as it is a relatively small and simple project to build.

    Download https://gitlab.com/BuildStream/buildstream/raw/master/integration-tests/cmake-test/src/step7.tar.gz

    This should provide you with `step7.tar.gz`

    Move `step7.tar.gz` to `src`


    Download https://gitlab.com/BuildStream/buildstream/raw/master/integration-tests/cmake-test/keys/gnome-sdk.gpg

    This should provide you with `gnome-sdk.gpg`

    Move `gnome-sdk.gpg` to `keys`

----

Alternatively, you can link to your project using one of the options in sources or tar.gz your projects and use it in place of step7.tar.gz


Creating the project files
----

Project.conf
~~~~

In the root of the project directory create a file called project.conf containing::

  name: ProjectName  # The name you want to give to your project
  element-path: elementsPath # The relative path to the "elements" directory
  # The elements directory is where your .bst files will be stored 
  aliases:
    name:url # This is used so you can moderate the URLs/Repos used by your build. 
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

In the elements directory Create a file called step7.bst containing::

  kind: cmake #This is an element plugin (linked below)
  description: Cmake test
  
  depends:
    - filename: dependencies/base-platform.bst
      type: build
    - filename: dependencies/base-sdk.bst
      type: build
  
  sources:
    - kind: tar #This is a Source Plugin
      url: file:/src/step7.tar.gz
  
:ref:`plugins_elements:`

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
  config:
    source: files
    target: usr

:ref:`format_config`

base-platform.bst
~~~~

In the elements/dependencies directory Create a file called base-platform.bst containing::

  kind: import
  description: Import the base freedesktop platform
  sources:
  - kind: ostree
    url: gnomesdk:repo/
    gpg-key: keys/gnome-sdk.gpg
    track: runtime/org.freedesktop.BasePlatform/x86_64/1.4
  config:
    source: files
  public:
    bst:
      integration-commands:
      - ldconfig

:ref:`format_public` 

Building
----

From the project root directory run:

  ``bst`` :ref:`invoking_build` ``step7.bst``
  
You can substitute step7.bst for your own .bst file

