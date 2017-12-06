.. _createproject:

Creating a basic project
====

This Section assumes you have installed Buildstream already.

If not, go to :ref:`install`

Or :ref:`docker`

This section will be using files from: 

https://gitlab.com/BuildStream/buildstream/tree/master/integration-tests/cmake-test/

Setup
----

If using docker, run::

  bst-here 

in the directory you want to use

Create a project directory and in it create the following directories:
    elements, elements/dependencies, keys, src

install wget or some other download tool

----

For this example we will be using cmake-test,
as it is a relatively small and simple project to build

Download https://gitlab.com/BuildStream/buildstream/raw/master/integration-tests/cmake-test/src/step7.tar.gz

This should provide you with step7.tar.gz

Move step7.tar.gz to src

----

Download https://gitlab.com/BuildStream/buildstream/raw/master/integration-tests/cmake-test/keys/gnome-sdk.gpg

This should provide you with gnome-sdk.gpg

Move gnome-sdk.gpg to keys

Creating the project files
----

Project.conf
~~~~

In the root of the project directory create a file called project.conf containing::

  name: ProjectName  #The name you want to give to your project
  element-path: elementsPath #The path to the "elements" directory
  aliases:
    name:url #This is used so you can moderate the URLs/Repos used by your build. 
             #This way, they can be modified in a single place instead of multiple

step7.bst
~~~~

In the elements directory Create a file called step7.bst containing::

  kind: cmake
  description: Cmake test
  
  depends:
    - filename: dependencies/base-platform.bst
      type: build
    - filename: dependencies/base-sdk.bst
      type: build
  
  sources:
    - kind: tar
      url: file:/src/step7.tar.gz
      ref: 9591707afbae77751730b4af4c52a18b1cdc4378237bc64055f099bc95c330db
  
:ref:`format_kind`

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
    ref: c9d09b7250a12ef09d95952fc4f49a35e5f8c2c1dd7141b7eeada4069e6f6576
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

