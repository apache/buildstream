

.. _getting_started:

Getting started
===============


Motivation
----------
Build tools are used to automate the creation of a software build and the associated processes.
They are essential in environments where there are many, inter-connected projects as it gets hard
to keep track of: what needs to be built, in what sequence things need to be built, and what
*dependencies* (files/packages that are required in order for an application to run) there
are in the process. Using a build tool allows this process to become more consistent.

In addition to this, large projects are typically built in various ways, which means that the
project may invoke more than one build tool.
BuildStream hopes to centralise all of this so that users need only maintain one
single set of core module metadata in one repository, in the same declarative YAML format.


"So, what is BuildStream?"
--------------------------
BuildStream is a command line tool that executes software build and integration pipelines - it is
**NOT** a build tool, rather, an integration tool which can delegate the building of software
to other build tools.
Builds are produced in a sandboxed environment which does not allow access to the host OS, this
guarantees the reproducibility of builds and allows for build results to be shared between multiple
developers.


Basic concepts of BuildStream
-----------------------------
The command line executable for BuildStream is: `bst`. We execute this command
when operating within a **project**, where a project contains **elements**. Elements describe
*how* we should build a component of the software-stack from its **sources**.

Projects can be of any size and can also depend on other BuildStream projects. It is
recommended to keep each project in a separate Git repository. 

The top-level directory of the project is marked by a `project.conf` file, which sets the
project-wide configuration options and is written in YAML format. To reemphasise, `bst`
commands should be run from this directory.

Elements are typically stored in a project's sub-directory aptly named *elements*. In this
directory each element is represented by a *.bst* file. *.bst* files use YAML syntax.

Within an element (*.bst* file), there are various attributes (nodes) that authors
can control. However, it should be noted that BuildStream aims to provide sensible default
values for attributes that are not explicitly set/declared by the user.
