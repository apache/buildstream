.. _public:


Builtin Public Data
===================

Elements can provide public data which can be read by other elements
later in the pipeline, the format for exposing public data on a given
element is :ref:`described here <format_public>`.

Any element may use public data for whatever purpose it wants, but
BuildStream has some built-in expectations of public data, which resides
completely in the ``bst`` domain.

In this section we will describe the public data in the ``bst`` domain.


.. _public_integration:

Integration Commands
--------------------

.. code:: yaml

   # Specify some integration commands
   public:
     bst:
       integration-commands:
       - /usr/bin/update-fancy-feature-cache

The built-in ``integration-commands`` list indicates that depending elements
should run this set of commands before expecting the staged runtime environment
to be functional.

Typical cases for this include running ``ldconfig`` at the base of a pipeline,
or running commands to update various system caches.

Integration commands of a given element are automatically run by the
:func:`Element.integrate() <buildstream.element.Element.integrate>` method
and are used by various plugins.

Notably the :mod:`BuildElement <buildstream.buildelement>` derived classes
will always integrate the build dependencies after staging and before running
any build commands.


.. _public_split_rules:

Split Rules
-----------

.. code:: yaml

   # Specify some split rules
   public:
     bst:
       split-rules:
         runtime:
         - |
           %{bindir}/*
         - |
           %{sbindir}/*
         - |
           %{libexecdir}/*
         - |
           %{libdir}/lib*.so*

Split rules indicate how the output of an element can be categorized
into *domains*.

The ``split-rules`` domains are used by the
:func:`Element.stage_artifact() <buildstream.element.Element.stage_artifact>`
method when deciding what domains of an artifact should be staged.

The strings listed in each domain are first substituted with the
:ref:`variables <format_variables>` in context of the given element, and
then applied as a glob style match, as understood by
:func:`utils.glob() <buildstream.utils.glob>`

This is used for creating compositions with the :mod:`compose <elements.compose>`
element and can be used by other deployment related elements for the purpose of
splitting element artifacts into separate packages.
