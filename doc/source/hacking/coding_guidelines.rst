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



.. _coding_guidelines:

Coding guidelines
-----------------
This section discusses coding style and other guidelines for hacking
on BuildStream. This is important to read through for writing any non-trivial
patches and especially outlines what people should watch out for when
reviewing patches.

Much of the rationale behind what is layed out in this section considers
good traceability of lines of code with *git blame*, overall sensible
modular structure, consistency in how we write code, and long term maintenance
in mind.


Approximate PEP-8 Style
~~~~~~~~~~~~~~~~~~~~~~~
Python coding style for BuildStream is approximately `pep8 <https://www.python.org/dev/peps/pep-0008/>`_.

The coding style is automatically enforced by `black <https://black.readthedocs.io/en/stable/>`_.

Formatting will be checked automatically when running the testsuite on CI. For
details on how to format your code locally, see :ref:`formatting code <contributing_formatting_code>`.


.. _contributing_documenting_symbols:

Documenting symbols
~~~~~~~~~~~~~~~~~~~
In BuildStream, we maintain what we call a *"Public API Surface"* that
is guaranteed to be stable and unchanging across stable releases. The
symbols which fall into this special class are documented using Python's
standard *docstrings*, while all other internals of BuildStream are documented
with comments above the related symbol.

When documenting the public API surface which is rendered in the reference
manual, we always mention the major version in which the API was introduced,
as shown in the examples below. If a public API exists without the *Since*
annotation, this is taken to mean that it was available since the first stable
major point release (e.g: 2.0).

We also always ensure that the **public API** is entirely typed using type
annotations inline.

The private API *can* be typed inline or in the documentation at the author's
discretion.

.. note::

  Types are checked using `mypy`. You can run it like :command:`tox -e mypy`

Here are some examples to get the hang of the format of API documenting
comments and docstrings.

**Public API Surface method**::

  def frobnicate(self, source: Source, *, frobilicious: bool = False) -> Element:
      """Frobnicates this element with the specified source

      Args:
         source: The Source to frobnicate with
         frobilicious: Optionally specify that frobnication should be
                              performed frobiliciously

      Returns:
         The frobnicated version of this Element.

      *Since: 2.2*
      """
      ...

**Internal method**::

  # frobnicate():
  #
  # Frobnicates this element with the specified source
  #
  # Args:
  #    source: The Source to frobnicate with
  #    frobilicious: Optionally specify that frobnication should be
  #                         performed frobiliciously
  #
  # Returns:
  #    The frobnicated version of this Element.
  #
  def frobnicate(self, source: Source, *, frobilicious: bool = False) -> Element:
      ...

**Public API Surface instance variable**::

  def __init__(self, context, element):

    self.name = self._compute_name(context, element)
    """The name of this foo

    *Since: 2.2*
    """

.. note::

   Python does not support docstrings on instance variables, but sphinx does
   pick them up and includes them in the generated documentation.

**Internal instance variable**::

  def __init__(self, context, element):

    self.name = self._compute_name(context, element)  # The name of this foo

**Internal instance variable (long)**::

  def __init__(self, context, element):

    # This instance variable required a longer explanation, so
    # it is on a line above the instance variable declaration.
    self.name = self._compute_name(context, element)


**Public API Surface class**::

  class Foo(Bar):
      """The main Foo object in the data model

      Explanation about Foo. Note that we always document
      the constructor arguments here, and not beside the __init__
      method.

      Args:
         context: The invocation Context
         count: The number to count

      *Since: 2.2*
      """
      def __init__(self, context: Context, count: int) -> None:
      ...

**Internal class**::

  # Foo()
  #
  # The main Foo object in the data model
  #
  # Args:
  #    context (Context): The invocation Context
  #    count (int): The number to count
  #
  class Foo(Bar):
      ...


.. _contributing_class_order:

Class structure and ordering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
When creating or modifying an object class in BuildStream, it is
important to keep in mind the order in which symbols should appear
and keep this consistent.

Here is an example to illustrate the expected ordering of symbols
on a Python class in BuildStream::

  class Foo(Bar):

      # Public class-wide variables come first, if any.

      # Private class-wide variables, if any

      # Now we have the dunder/magic methods, always starting
      # with the __init__() method.

      def __init__(self, name):

          super().__init__()

          # NOTE: In the instance initializer we declare any instance variables,
          #       always declare the public instance variables (if any) before
          #       the private ones.
          #
          #       It is preferred to avoid any public instance variables, and
          #       always expose an accessor method for it instead.

          #
          # Public instance variables
          #
          self.name = name  # The name of this foo

          #
          # Private instance variables
          #
          self._count = 0   # The count of this foo

      ################################################
      #               Abstract Methods               #
      ################################################

      # NOTE: Abstract methods in BuildStream are allowed to have
      #       default methods.
      #
      #       Subclasses must NEVER override any method which was
      #       not advertized as an abstract method by the parent class.

      # frob()
      #
      # Implementors should implement this to frob this foo
      # count times if possible.
      #
      # Args:
      #    count (int): The number of times to frob this foo
      #
      # Returns:
      #    (int): The number of times this foo was frobbed.
      #
      # Raises:
      #    (FooError): Implementors are expected to raise this error
      #
      def frob(self, count):

          #
          # An abstract method in BuildStream is allowed to have
          # a default implementation.
          #
          self._count = self._do_frobbing(count)

          return self._count

      ################################################
      #     Implementation of abstract methods       #
      ################################################

      # NOTE: Implementations of abstract methods defined by
      #       the parent class should NEVER document the API
      #       here redundantly.

      def frobbish(self):
         #
         # Implementation of the "frobbish" abstract method
         # defined by the parent Bar class.
         #
         return True

      ################################################
      #                 Public Methods               #
      ################################################

      # NOTE: Public methods here are the ones which are expected
      #       to be called from outside of this class.
      #
      #       These, along with any abstract methods, usually
      #       constitute the API surface of this class.

      # frobnicate()
      #
      # Perform the frobnication process on this Foo
      #
      # Raises:
      #    (FrobError): In the case that a frobnication error was
      #                 encountered
      #
      def frobnicate(self):
          frobnicator.frobnicate(self)

      # set_count()
      #
      # Sets the count of this foo
      #
      # Args:
      #    count (int): The new count to set
      #
      def set_count(self, count):

          self._count = count

      # get_count()
      #
      # Accessor for the count value of this foo.
      #
      # Returns:
      #    (int): The count of this foo
      #
      def get_count(self, count):

          return self._count

      ################################################
      #                 Private Methods              #
      ################################################

      # NOTE: Private methods are the ones which are internal
      #       implementation details of this class.
      #
      #       Even though these are private implementation
      #       details, they still MUST have API documenting
      #       comments on them.

      # _do_frobbing()
      #
      # Does the actual frobbing
      #
      # Args:
      #    count (int): The number of times to frob this foo
      #
      # Returns:
      #    (int): The number of times this foo was frobbed.
      #
      def self._do_frobbing(self, count):
          return count


.. _contributing_public_and_private:

Public and private symbols
~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream mostly follows the PEP-8 for defining *public* and *private* symbols
for any given class, with some deviations. Please read the `section on inheritance
<https://www.python.org/dev/peps/pep-0008/#designing-for-inheritance>`_ for
reference on how the PEP-8 defines public and non-public.

* A *public* symbol is any symbol which you expect to be used by clients
  of your class or module within BuildStream.

  Public symbols are written without any leading underscores.

* A *private* symbol is any symbol which is entirely internal to your class
  or module within BuildStream. These symbols cannot ever be accessed by
  external clients or modules.

  A private symbol must be denoted by a leading underscore.

* When a class can have subclasses, then private symbols should be denoted
  by two leading underscores. For example, the ``Sandbox`` or ``Platform``
  classes which have various implementations, or the ``Element`` and ``Source``
  classes which plugins derive from.

  The double leading underscore naming convention invokes Python's name
  mangling algorithm which helps prevent namespace collisions in the case
  that subclasses might have a private symbol with the same name.

In BuildStream, we have what we call a *"Public API Surface"*, as previously
mentioned in :ref:`contributing_documenting_symbols`. In the :ref:`next section
<contributing_public_api_surface>` we will discuss the *"Public API Surface"* and
outline the exceptions to the rules discussed here.


.. _contributing_public_api_surface:

Public API surface
~~~~~~~~~~~~~~~~~~
BuildStream exposes what we call a *"Public API Surface"* which is stable
and unchanging. This is for the sake of stability of the interfaces which
plugins use, so it can also be referred to as the *"Plugin facing API"*.

Any symbols which are a part of the *"Public API Surface*" are never allowed
to change once they have landed in a stable release version of BuildStream. As
such, we aim to keep the *"Public API Surface"* as small as possible at all
times, and never expose any internal details to plugins inadvertently.

One problem which arises from this is that we end up having symbols
which are *public* according to the :ref:`rules discussed in the previous section
<contributing_public_and_private>`, but must be hidden away from the
*"Public API Surface"*. For example, BuildStream internal classes need
to invoke methods on the ``Element`` and ``Source`` classes, whereas these
methods need to be hidden from the *"Public API Surface"*.

This is where BuildStream deviates from the PEP-8 standard for public
and private symbol naming.

In order to disambiguate between:

* Symbols which are publicly accessible details of the ``Element`` class, can
  be accessed by BuildStream internals, but must remain hidden from the
  *"Public API Surface"*.

* Symbols which are private to the ``Element`` class, and cannot be accessed
  from outside of the ``Element`` class at all.

We denote the former category of symbols with only a single underscore, and the latter
category of symbols with a double underscore. We often refer to this distinction
as *"API Private"* (the former category) and *"Local Private"* (the latter category).

Classes which are a part of the *"Public API Surface"* and require this disambiguation
were not discussed in :ref:`the class ordering section <contributing_class_order>`, for
these classes, the *"API Private"* symbols always come **before** the *"Local Private"*
symbols in the class declaration.

Modules which are not a part of the *"Public API Surface"* have their Python files
prefixed with a single underscore, and are not imported in BuildStream's the master
``__init__.py`` which is used by plugins.

.. note::

   The ``utils.py`` module is public and exposes a handful of utility functions,
   however many of the functions it provides are *"API Private"*.

   In this case, the *"API Private"* functions are prefixed with a single underscore.

Any objects which are a part of the *"Public API Surface"* should be exposed via the
toplevel ``__init__.py`` of the ``buildstream`` package.


File naming convention
~~~~~~~~~~~~~~~~~~~~~~
With the exception of a few helper objects and data structures, we structure
the code in BuildStream such that every filename is named after the object it
implements. E.g. The ``Project`` object is implemented in ``_project.py``, the
``Context`` object in ``_context.py``, the base ``Element`` class in ``element.py``,
etc.

As mentioned in the previous section, objects which are not a part of the
:ref:`public, plugin facing API surface <contributing_public_api_surface>` have their
filenames prefixed with a leading underscore (like ``_context.py`` and ``_project.py``
in the examples above).

When an object name has multiple words in it, e.g. ``ArtifactCache``, then the
resulting file is named all in lower case without any underscore to separate
words. In the case of ``ArtifactCache``, the filename implementing this object
is found at ``_artifactcache/artifactcache.py``.


Imports
~~~~~~~
Module imports inside BuildStream are done with relative ``.`` notation:

**Good**::

  from ._context import Context

**Bad**::

  from buildstream._context import Context

The exception to the above rule is when authoring plugins,
plugins do not reside in the same namespace so they must
address buildstream in the imports.

An element plugin will derive from Element by importing::

  from buildstream import Element

When importing utilities specifically, don't import function names
from there, instead import the module itself::

  from . import utils

This makes things clear when reading code that said functions
are not defined in the same file but come from utils.py for example.


.. _contributing_instance_variables:

Instance variables
~~~~~~~~~~~~~~~~~~
It is preferred that all instance state variables be declared as :ref:`private symbols
<contributing_public_and_private>`, however in some cases, especially when the state
is immutable for the object's life time (like an ``Element`` name for example), it
is acceptable to save some typing by using a publicly accessible instance variable.

It is never acceptable to modify the value of an instance variable from outside
of the declaring class, even if the variable is *public*. In other words, the class
which exposes an instance variable is the only one in control of the value of this
variable.

* If an instance variable is public and must be modified; then it must be
  modified using a :ref:`mutator <contributing_accessor_mutator>`.

* Ideally for better encapsulation, all object state is declared as
  :ref:`private instance variables <contributing_public_and_private>` and can
  only be accessed by external classes via public :ref:`accessors and mutators
  <contributing_accessor_mutator>`.

.. note::

   In some cases, we may use small data structures declared as objects for the sake
   of better readability, where the object class itself has no real supporting code.

   In these exceptions, it can be acceptable to modify the instance variables
   of these objects directly, unless they are otherwise documented to be immutable.


.. _contributing_accessor_mutator:

Accessors and mutators
~~~~~~~~~~~~~~~~~~~~~~
An accessor and mutator, are methods defined on the object class to access (get)
or mutate (set) a value owned by the declaring class, respectively.

An accessor might derive the returned value from one or more of its components,
and a mutator might have side effects, or delegate the mutation to a component.

Accessors and mutators are always :ref:`public <contributing_public_and_private>`
(even if they might have a single leading underscore and are considered
:ref:`API Private <contributing_public_api_surface>`), as their purpose is to
enforce encapsulation with regards to any accesses to the state which is owned
by the declaring class.

Accessors and mutators are functions prefixed with ``get_`` and ``set_``
respectively, e.g.::

  class Foo():

      def __init__(self):

          # Declare some internal state
          self._count = 0

      # get_count()
      #
      # Gets the count of this Foo.
      #
      # Returns:
      #    (int): The current count of this Foo
      #
      def get_foo(self):
          return self._count

      # set_count()
      #
      # Sets the count of this Foo.
      #
      # Args:
      #    count (int): The new count for this Foo
      #
      def set_foo(self, count):
          self._count = count

.. attention::

   We are aware that Python offers a facility for accessors and
   mutators using the ``@property`` decorator instead. Do not use
   the ``@property`` decorator.

   The decision to use explicitly defined functions instead of the
   ``@property`` decorator is rather arbitrary, there is not much
   technical merit to preferring one technique over the other.
   However as :ref:`discussed below <contributing_always_consistent>`,
   it is of the utmost importance that we do not mix both techniques
   in the same codebase.


.. _contributing_abstract_methods:

Abstract methods
~~~~~~~~~~~~~~~~
In BuildStream, an *"Abstract Method"* is a bit of a misnomer and does
not match up to how Python defines abstract methods, we need to seek out
a new nomenclature to refer to these methods.

In Python, an *"Abstract Method"* is a method which **must** be
implemented by a subclass, whereas all methods in Python can be
overridden.

In BuildStream, we use the term *"Abstract Method"*, to refer to
a method which **can** be overridden by a subclass, whereas it
is **illegal** to override any other method.

* Abstract methods are allowed to have default implementations.

* Subclasses are not allowed to redefine the calling signature
  of an abstract method, or redefine the API contract in any way.

* Subclasses are not allowed to override any other methods.

The key here is that in BuildStream, we consider it unacceptable
that a subclass overrides a method of its parent class unless
the said parent class has explicitly given permission to subclasses
to do so, and outlined the API contract for this purpose. No surprises
are allowed.


Error handling
~~~~~~~~~~~~~~
In BuildStream, all non recoverable errors are expressed via
subclasses of the ``BstError`` exception.

This exception is handled deep in the core in a few places, and
it is rarely necessary to handle a ``BstError``.


Raising exceptions
''''''''''''''''''
When writing code in the BuildStream core, ensure that all system
calls and third party library calls are wrapped in a ``try:`` block,
and raise a descriptive ``BstError`` of the appropriate class explaining
what exactly failed.

Ensure that the original system call error is formatted into your new
exception, and that you use the Python ``from`` semantic to retain the
original call trace, example::

  try:
      os.utime(self._refpath(ref))
  except FileNotFoundError as e:
      raise ArtifactError("Attempt to access unavailable artifact: {}".format(e)) from e


Enhancing exceptions
''''''''''''''''''''
Sometimes the ``BstError`` originates from a lower level component,
and the code segment which raised the exception did not have enough context
to create a complete, informative summary of the error for the user.

In these cases it is necessary to handle the error and raise a new
one, e.g.::

  try:
      extracted_artifact = self._artifacts.extract(self, cache_key)
  except ArtifactError as e:
      raise ElementError("Failed to extract {} while checking out {}: {}"
                         .format(cache_key, self.name, e)) from e


Programming errors
''''''''''''''''''
Sometimes you are writing code and have detected an unexpected condition,
or a broken invariant for which the code cannot be prepared to handle
gracefully.

In these cases, do **not** raise any of the ``BstError`` class exceptions.

Instead, use the ``assert`` statement, e.g.::

  assert utils._is_main_process(), \
      "Attempted to save workspace configuration from child process"

This will result in a ``BUG`` message with the stack trace included being
logged and reported in the frontend.


BstError parameters
'''''''''''''''''''
When raising ``BstError`` class exceptions, there are some common properties
which can be useful to know about:

* **message:** The brief human readable error, will be formatted on one line in the frontend.

* **detail:** An optional detailed human readable message to accompany the **message** summary
  of the error. This is often used to recommend the user some course of action, or to provide
  additional context about the error.

* **temporary:** Some errors are allowed to be *temporary*, this attribute is only
  observed from child processes which fail in a temporary way. This distinction
  is used to determine whether the task should be *retried* or not. An error is usually
  only a *temporary* error if the cause of the error was a network timeout.

* **reason:** A machine readable identifier for the error. This is used for the purpose
  of regression testing, such that we check that BuildStream has errored out for the
  expected reason in a given failure mode.


Documenting Exceptions
''''''''''''''''''''''
We have already seen :ref:`some examples <contributing_class_order>` of how
exceptions are documented in API documenting comments, but this is worth some
additional disambiguation.

* Only document the exceptions which are raised directly by the function in question.
  It is otherwise nearly impossible to keep track of what exceptions *might* be raised
  indirectly by calling the given function.

* For a regular public or private method, your audience is a caller of the function;
  document the exception in terms of what exception might be raised as a result of
  calling this method.

* For an :ref:`abstract method <contributing_abstract_methods>`, your audience is the
  implementor of the method in a subclass; document the exception in terms of what
  exception is prescribed for the implementing class to raise.


.. _contributing_always_consistent:

Always be consistent
~~~~~~~~~~~~~~~~~~~~
There are various ways to define functions and classes in Python,
which has evolved with various features over time.

In BuildStream, we may not have leveraged all of the nice features
we could have, that is okay, and where it does not break API, we
can consider changing it.

Even if you know there is a *better* way to do a given thing in
Python when compared to the way we do it in BuildStream, *do not do it*.

Consistency of how we do things in the codebase is more important
than the actual way in which things are done, always.

Instead, if you like a certain Python feature and think the BuildStream
codebase should use it, then propose your change on the `mailing list
<https://lists.apache.org/list.html?dev@buildstream.apache.org>`_. Chances
are that we will reach agreement to use your preferred approach, and
in that case, it will be important to apply the change unilaterally
across the entire codebase, such that we continue to have a consistent
codebase.


Avoid tail calling
~~~~~~~~~~~~~~~~~~
With the exception of tail calling with simple functions from
the standard Python library, such as splitting and joining lines
of text and encoding/decoding text; always avoid tail calling.

**Good**::

  # Variables that we will need declared up top
  context = self._get_context()
  workspaces = context.get_workspaces()

  ...

  # Saving the workspace configuration
  workspaces.save_config()

**Bad**::

  # Saving the workspace configuration
  self._get_context().get_workspaces().save_config()

**Acceptable**::

  # Decode the raw text loaded from a log file for display,
  # join them into a single utf-8 string and strip away any
  # trailing whitespace.
  return '\n'.join([line.decode('utf-8') for line in lines]).rstrip()

When you need to obtain a delegate object via an accessor function,
either do it at the beginning of the function, or at the beginning
of a code block within the function that will use that object.

There are several reasons for this convention:

* When observing a stack trace, it is always faster and easier to
  determine what went wrong when all statements are on separate lines.

* We always want individual lines to trace back to their origin as
  much as possible for the purpose of tracing the history of code
  with *git blame*.

  One day, you might need the ``Context`` or ``Workspaces`` object
  in the same function for another reason, at which point it will
  be unacceptable to leave the existing line as written, because it
  will introduce a redundant accessor to the same object, so the
  line written as::

    self._get_context().get_workspaces().save_config()

  Will have to change at that point, meaning we lose the valuable
  information of which commit originally introduced this call
  when running *git blame*.

* For similar reasons, we prefer delegate objects be accessed near
  the beginning of a function or code block so that there is less
  chance that this statement will have to move in the future, if
  the same function or code block needs the delegate object for any
  other reason.

  Asides from this, code is generally more legible and uniform when
  variables are declared at the beginning of function blocks.


Vertical stacking of modules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
For the sake of overall comprehensiveness of the BuildStream
architecture, it is important that we retain vertical stacking
order of the dependencies and knowledge of modules as much as
possible, and avoid any cyclic relationships in modules.

For instance, the ``Source`` objects are owned by ``Element``
objects in the BuildStream data model, and as such the ``Element``
will delegate some activities to the ``Source`` objects in its
possession. The ``Source`` objects should however never call functions
on the ``Element`` object, nor should the ``Source`` object itself
have any understanding of what an ``Element`` is.

If you are implementing a low level utility layer, for example
as a part of the ``YAML`` loading code layers, it can be tempting
to derive context from the higher levels of the codebase which use
these low level utilities, instead of defining properly stand alone
APIs for these utilities to work: Never do this.

Unfortunately, unlike other languages where include files play
a big part in ensuring that it is difficult to make a mess; Python,
allows you to just call methods on arbitrary objects passed through
a function call without having to import the module which defines
those methods - this leads to cyclic dependencies of modules quickly
if the developer does not take special care of ensuring this does not
happen.


Minimize arguments in methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
When creating an object, or adding a new API method to an existing
object, always strive to keep as much context as possible on the
object itself rather than expecting callers of the methods to provide
everything the method needs every time.

If the value or object that is needed in a function call is a constant
for the lifetime of the object which exposes the given method, then
that value or object should be passed in the constructor instead of
via a method call.


Minimize API surfaces
~~~~~~~~~~~~~~~~~~~~~
When creating an object, or adding new functionality in any way,
try to keep the number of :ref:`public, outward facing <contributing_public_and_private>`
symbols to a minimum, this is important for both
:ref:`internal and public, plugin facing API surfaces <contributing_public_api_surface>`.

When anyone visits a file, there are two levels of comprehension:

* What do I need to know in order to *use* this object.

* What do I need to know in order to *modify* this object.

For the former, we want the reader to understand with as little effort
as possible, what the public API contract is for a given object and consequently,
how it is expected to be used. This is also why we
:ref:`order the symbols of a class <contributing_class_order>` in such a way
as to keep all outward facing public API surfaces at the top of the file, so that the
reader never needs to dig deep into the bottom of the file to find something they
might need to use.

For the latter, when it comes to having to modify the file or add functionality,
you want to retain as much freedom as possible to modify internals, while
being sure that nothing external will be affected by internal modifications.
Less client facing API means that you have less surrounding code to modify
when your API changes. Further, ensuring that there is minimal outward facing
API for any module minimizes the complexity for the developer working on
that module, by limiting the considerations needed regarding external side
effects of their modifications to the module.

When modifying a file, one should not have to understand or think too
much about external side effects, when the API surface of the file is
well documented and minimal.

When adding new API to a given object for a new purpose, consider whether
the new API is in any way redundant with other API (should this value now
go into the constructor, since we use it more than once? could this
value be passed along with another function, and the other function renamed,
to better suit the new purposes of this module/object?) and repurpose
the outward facing API of an object as a whole every time.


Avoid transient state on instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
At times, it can be tempting to store transient state that is
the result of one operation on an instance, only to be retrieved
later via an accessor function elsewhere.

As a basic rule of thumb, if the value is transient and just the
result of one operation, which needs to be observed directly after
by another code segment, then never store it on the instance.

BuildStream is complicated in the sense that it is multi processed
and it is not always obvious how to pass the transient state around
as a return value or a function parameter. Do not fall prey to this
obstacle and pollute object instances with transient state.

Instead, always refactor the surrounding code so that the value
is propagated to the desired end point via a well defined API, either
by adding new code paths or changing the design such that the
architecture continues to make sense.


Refactor the codebase as needed
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Especially when implementing features, always move the BuildStream
codebase forward as a whole.

Taking a short cut is alright when prototyping, but circumventing
existing architecture and design to get a feature implemented without
re-designing the surrounding architecture to accommodate the new
feature instead, is never acceptable upstream.

For example, let's say that you have to implement a feature and you've
successfully prototyped it, but it launches a ``Job`` directly from a
``Queue`` implementation to get the feature to work, while the ``Scheduler``
is normally responsible for dispatching ``Jobs`` for the elements on
a ``Queue``. This means that you've proven that your feature can work,
and now it is time to start working on a patch for upstream.

Consider what the scenario is and why you are circumventing the design,
and then redesign the ``Scheduler`` and ``Queue`` objects to accommodate for
the new feature and condition under which you need to dispatch a ``Job``,
or how you can give the ``Queue`` implementation the additional context it
needs.
