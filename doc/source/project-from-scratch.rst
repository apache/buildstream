.. _project_from_scratch:

How to set up a buildstream repo
================================

Overview
--------

Buildstream operates out of a directory that contains a file named "project.conf", and contains within it a collection of ".bst" files which defines how to build an artifact.
For convenience, we put "project.conf" in the root of a git repository, and all of the ".bst" files are arranged in a subdirectory.

Creating the git repository
---------------------------

If you are using a git hosting service, follow their instructions for how to create a git repository.

If not:

1. Create your directory, e.g.
   ::
       mkdir buildstream-repo

2. Initialize the git repo, e.g.
   ::
       cd buildstream-repo
       git init

3. Set the remote to push to/pull from. For example, if there's a git server serving a repository to "git://git.example.org/buildstream-repo", the command to set the remote would be
   ::
       git remote add origin git://git.example.org/buildstream-repo

Setting up project.conf
-----------------------

The bare minimum a project.conf requires is a "name" and an "element-path".

"name" is the name of the project. This is used to make sure that artifacts from separate projects don't get mixed together in the cache.

"element-path" is the path to where the elements are stored, relative to the directory that contains project.conf. In the name of tidiness, this is usually a subdirectory called "elements", but for simplicity, we'll set it to the current directory.

minimal project.conf
~~~~~~~~~~~~~~~~~~~~
So a simple project.conf would look like ::

  cat >project.conf <<EOF
  name: test
  element-path: elements
  EOF

This specifies that elements live in a subdirectory called "elements" ::

  mkdir elements

Creating elements
-----------------

There are a wide variety of elements at your disposal, full documentation of all the elements is at https://buildstream.gitlab.io/buildstream/#elements.

Ultimately, the lowest-level element of buildstream is an "import" element. This is because buildstream scrupulously prevents the host's environment from affecting builds by running everything inside a sandbox. The downside of this is that they need a suite of tools to be provided before they can do anything.

The "import" element is used to take a source and provide the files in that source as an artifact.

minimal tar import element
~~~~~~~~~~~~~~~~~~~~~~~~~~

For example, a minimal build environment hosted somewhere as a tarball ::

  cat > elements/base.bst <<EOF
  kind: import
  description: Import a tarball as a build environment
  sources:
  - kind: tar
    url: http://www.example.com/x86-build-env.tar.gz
    ref: 0123456789abcdef
  EOF

arch-specific tar import element
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If this repository is going to be used for multiple architectures, it would look like ::

  cat > elements/base.bst <<EOF
  kind: import
  description: Import a tarball as a build environment
  arches:
    x86_64:
      sources:
      - kind: tar
        url: http://www.example.com/x86_64-build-env.tar.gz
        ref: 0123456789abcdef
    i386:
      sources:
      - kind: tar
        url: http://www.example.com/x86_32-build-env.tar.gz
        ref: fdecba987654321
  EOF

ostree import element
~~~~~~~~~~~~~~~~~~~~~

Buildstream typically uses an ostree repo for the minimal build environment, which looks like ::

  cat > elements/ostree-base.bst <<EOF
  kind: import
  description: Import the base freedesktop platform
  environment:
    PATH: /tools/bin:/tools/sbin:/usr/bin:/bin:/usr/sbin:/sbin
  public:
    bst:
      integration-commands:
      - ldconfig
  host-arches:
    x86_64:
      sources:
      - kind: ostree
        url: https://ostree.baserock.org/cache/
        track: baserock/bootstrap-stage3-sysroot/12c20460fb3c3c50d0ed9133aa19839a89626c0d66736c439c3deb0b66263684
        ref: 4788d14185c415c9cef20a1d36286d792dac7a3271504e21c6903987221bfccd
      config:
        source: files
    ppc64b:
      sources:
      - kind: ostree
        url: https://ostree.baserock.org/cache/
        track: baserock/bootstrap-stage3-sysroot/04e669a8a1b0252ac6307dc268afc4e5f472baeec8ba664bdccae9e612c86d69
        ref: 4bbdb9fff190f52d5534efe4e2f35ef701cf741254399639bcf9c52c94e5f030
      config:
        source: files
  EOF

A test element
~~~~~~~~~~~~~~

Now that we have a build environment, we can start creating elements. For this experiment, I'll write an element using shell scripts ::

  cat > elements/test-element.bst <<EOF
  kind: manual
  depends:
  - filename: ostree-base.bst
    type: build
  config:
    install-commands:
    - "mkdir -p %{install-root}"
    - "echo hello > %{install-root}/hello"
  EOF

Because test-element depends on ostree-base.bst, it will include that in the sandbox, providing enough tools to run shell commands like "mkdir" and "echo".

Running ``bst build test-element.bst`` will create an artifact in the cache that contains the file "hello". Note that all element paths are relative to the "elements" subdir.

You can inspect this file by checking out the element, e.g. ``bst checkout test-element.bst test`` will create a directory named "test", which contains a file called "hello"

A build element
~~~~~~~~~~~~~~~

In the real world, you'll be building real elements. The majority of the time, they build with a well-defined build system (e.g. autotools, cmake, qmake), will be made of a single source, and will have a number of dependencies. ::

  cat > elements/example-element.bst <<EOF
  # An element's kind determines its behaviour. "autotools" elements will try
  # to build the sources as if they are source code for autotools projects.
  kind: autotools
  description: An example of a build element.
  # This element depends on "base" to provide the necessary tools to compile
  # GNU hello. "type: build" means that "base" will only be imported into the
  # staging area when building this element.
  depends:
  - filename: ostree-base.bst
    type: build
  # We fetch a tar from gnu.org to build, ref is a sha256sum of the expected file,
  # so that you won't start building something unexpected.
  sources:
  - kind: tar
    url: http://ftp.gnu.org/gnu/hello/hello-2.10.tar.gz
    ref: 31e066137a962676e89f69d1b65382de95a7ef7d914b8cb956f41ea72e0f516b
  EOF

Creating your own build environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In many cases, you don't want to use the build environment provided in a "base" element. For example, if you want your system to use a specific libc that isn't provided by "base". 

In cases like these, you will want to build a new build environment from scratch inside buildstream.
For an example of this, see https://gitlab.com/baserock/definitions/tree/master/elements.
