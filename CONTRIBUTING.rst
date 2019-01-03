Contributing
============
Some tips and guidelines for developers hacking on BuildStream


.. _contributing_filing_issues:

Filing issues
-------------
If you are experiencing an issue with BuildStream, or would like to submit a patch
to fix an issue, then you should first search the list of `open issues <https://gitlab.com/BuildStream/buildstream/issues>`_
to see if the issue is already filed, and `open an issue <https://gitlab.com/BuildStream/buildstream/issues/new>`_
if no issue already exists.

For policies on how to submit an issue and how to use our project labels,
we recommend that you read the `policies guide
<https://gitlab.com/BuildStream/nosoftware/alignment/blob/master/BuildStream_policies.md>`_.


.. _contributing_fixing_bugs:

Fixing bugs
-----------
Before fixing a bug, it is preferred that an :ref:`issue be filed <contributing_filing_issues>`
first in order to better document the defect, however this need not be followed to the
letter for minor fixes.

Patches which fix bugs should always come with a regression test.


.. _contributing_adding_features:

Adding new features
-------------------
Feature additions should be proposed on the `mailing list
<https://mail.gnome.org/mailman/listinfo/buildstream-list>`_
before being considered for inclusion. To save time and avoid any frustration,
we strongly recommend proposing your new feature in advance of commencing work.

Once consensus has been reached on the mailing list, then the proposing
party should :ref:`file an issue <contributing_filing_issues>` to track the
work. Please use the *bst_task* template for issues which represent
feature additions.

New features must be well documented and tested in our test suite.

It is expected that the individual submitting the work take ownership
of their feature within BuildStream for a reasonable timeframe of at least
one release cycle after their work has landed on the master branch. This is
to say that the submitter is expected to address and fix any side effects,
bugs or regressions which may have fell through the cracks in the review
process, giving us a reasonable timeframe for identifying these.


.. _contributing_submitting_patches:

Submitting patches
------------------


Ask for developer access
~~~~~~~~~~~~~~~~~~~~~~~~
If you want to submit a patch, do ask for developer permissions, either
by asking us directly on our public IRC channel (irc://irc.gnome.org/#buildstream)
or by visiting our `project page on GitLab <https://gitlab.com/BuildStream/buildstream>`_
and using the GitLab UI to ask for permission.

This will make your contribution experience smoother, as you will not
need to setup any complicated CI settings, and rebasing your branch
against the upstream master branch will be more painless.


Branch names
~~~~~~~~~~~~
Branch names for merge requests should be prefixed with the submitter's
name or nickname, followed by a forward slash, and then a descriptive
name. e.g.::

  username/fix-that-bug

This allows us to more easily identify which branch does what and
belongs to whom, especially so that we can effectively cleanup stale
branches in the upstream repository over time.


Merge requests
~~~~~~~~~~~~~~
Once you have created a local branch, you can push it to the upstream
BuildStream repository using the command line::

  git push origin username/fix-that-bug:username/fix-that-bug

GitLab will respond to this with a message and a link to allow you to create
a new merge request. You can also `create a merge request for an existing branch
<https://gitlab.com/BuildStream/buildstream/merge_requests/new>`_.

You may open merge requests for the branches you create before you are ready
to have them reviewed and considered for inclusion if you like. Until your merge
request is ready for review, the merge request title must be prefixed with the
``WIP:`` identifier. GitLab `treats this specially
<https://docs.gitlab.com/ee/user/project/merge_requests/work_in_progress_merge_requests.html>`_,
which helps reviewers.

Consider marking a merge request as WIP again if you are taking a while to
address a review point. This signals that the next action is on you, and it
won't appear in a reviewer's search for non-WIP merge requests to review.


Organized commits
~~~~~~~~~~~~~~~~~
Submitted branches must not contain a history of the work done in the
feature branch. For example, if you had to change your approach, or
have a later commit which fixes something in a previous commit on your
branch, we do not want to include the history of how you came up with
your patch in the upstream master branch.

Please use git's interactive rebase feature in order to compose a clean
patch series suitable for submission upstream.

Every commit in series should pass the test suite, this is very important
for tracking down regressions and performing git bisections in the future.

We prefer that documentation changes be submitted in separate commits from
the code changes which they document, and newly added test cases are also
preferred in separate commits.

If a commit in your branch modifies behavior such that a test must also
be changed to match the new behavior, then the tests should be updated
with the same commit, so that every commit passes its own tests.

These principles apply whenever a branch is non-WIP. So for example, don't push
'fixup!' commits when addressing review comments, instead amend the commits
directly before pushing. GitLab has `good support
<https://docs.gitlab.com/ee/user/project/merge_requests/versions.html>`_ for
diffing between pushes, so 'fixup!' commits are not necessary for reviewers.


Commit messages
~~~~~~~~~~~~~~~
Commit messages must be formatted with a brief summary line, followed by
an empty line and then a free form detailed description of the change.

The summary line must start with what changed, followed by a colon and
a very brief description of the change.

If the commit fixes an issue, or is related to an issue; then the issue
number must be referenced in the commit message.

**Example**::

  element.py: Added the frobnicator so that foos are properly frobbed.

  The new frobnicator frobnicates foos all the way throughout
  the element. Elements that are not properly frobnicated raise
  an error to inform the user of invalid frobnication rules.

  Fixes #123

Note that the 'why' of a change is as important as the 'what'.

When reviewing this, folks can suggest better alternatives when they know the
'why'. Perhaps there are other ways to avoid an error when things are not
frobnicated.

When folks modify this code, there may be uncertainty around whether the foos
should always be frobnicated. The comments, the commit message, and issue #123
should shed some light on that.

In the case that you have a commit which necessarily modifies multiple
components, then the summary line should still mention generally what
changed (if possible), followed by a colon and a brief summary.

In this case the free form detailed description of the change should
contain a bullet list describing what was changed in each component
separately.

**Example**::

  artifact cache: Fixed automatic expiry in the local cache

    o _artifactcache/artifactcache.py: Updated the API contract
      of ArtifactCache.remove() so that something detailed is
      explained here.

    o _artifactcache/cascache.py: Adhere to the new API contract
      dictated by the abstract ArtifactCache class.

    o tests/artifactcache/expiry.py: Modified test expectations to
      match the new behavior.

  This is a part of #123


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

We have a couple of minor exceptions to this standard, we dont want to compromise
code readability by being overly restrictive on line length for instance.

The pep8 linter will run automatically when :ref:`running the test suite <contributing_testing>`.


Line lengths
''''''''''''
Regarding laxness on the line length in our linter settings, it should be clarified
that the line length limit is a hard limit which causes the linter to bail out
and reject commits which break the high limit - not an invitation to write exceedingly
long lines of code, comments, or API documenting docstrings.

Code, comments and docstrings should strive to remain written for approximately 80
or 90 character lines, where exceptions can be made when code would be less readable
when exceeding 80 or 90 characters (often this happens in conditional statements
when raising an exception, for example). Or, when comments contain a long link that
causes the given line to to exceed 80 or 90 characters, we don't want this to cause
the linter to refuse the commit.


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
release 1.0.

Here are some examples to get the hang of the format of API documenting
comments and docstrings.

**Public API Surface method**::

  def frobnicate(self, source, *, frobilicious=False):
      """Frobnicates this element with the specified source

      Args:
         source (Source): The Source to frobnicate with
         frobilicious (bool): Optionally specify that frobnication should be
                              performed fribiliciously

      Returns:
         (Element): The frobnicated version of this Element.

      *Since: 1.2*
      """
      ...

**Internal method**::

  # frobnicate():
  #
  # Frobnicates this element with the specified source
  #
  # Args:
  #    source (Source): The Source to frobnicate with
  #    frobilicious (bool): Optionally specify that frobnication should be
  #                         performed fribiliciously
  #
  # Returns:
  #    (Element): The frobnicated version of this Element.
  #
  def frobnicate(self, source, *, frobilicious=False):
      ...

**Public API Surface instance variable**::

  def __init__(self, context, element):

    self.name = self._compute_name(context, element)
    """The name of this foo

    *Since: 1.2*
    """

.. note::

   Python does not support docstrings on instance variables, but sphinx does
   pick them up and includes them in the generated documentation.

**Internal instance variable**::

  def __init__(self, context, element):

    self.name = self._compute_name(context, element) # The name of this foo

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
         context (Context): The invocation Context
         count (int): The number to count

      *Since: 1.2*
      """
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
to invoke methods on the ``Element`` and ``Source`` classes, wheras these
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

When importing utilities specifically, dont import function names
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
a new nomanclature to refer to these methods.

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
<https://mail.gnome.org/mailman/listinfo/buildstream-list>`_. Chances
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
possesion. The ``Source`` objects should however never call functions
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


Bump format version
~~~~~~~~~~~~~~~~~~~
In order for projects to assert that they have a new enough version
of BuildStream to use the new plugin, the ``BST_FORMAT_VERSION`` must
be incremented in the ``_versions.py`` file.

Remember to include in your plugin's main documentation, the format
version in which the plugin was introduced, using the standard annotation
which we use throughout the documentation, e.g.::

  .. note::

     The ``foo`` plugin is available since :ref:`format version 16 <project_format_version>`


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

See the ``tests/cachekey/update.py`` file for instructions on running the updater,
you need to run the updater to generate the ``.expected`` files and add the new
``.expected`` files in the same commit which extends the cache key test.


Protocol buffers
----------------
BuildStream uses protobuf and gRPC for serialization and communication with
artifact cache servers.  This requires ``.proto`` files and Python code
generated from the ``.proto`` files using protoc.  All these files live in the
``buildstream/_protos`` directory.  The generated files are included in the
git repository to avoid depending on grpcio-tools for user installations.


Regenerating code
~~~~~~~~~~~~~~~~~
When ``.proto`` files are modified, the corresponding Python code needs to
be regenerated.  As a prerequisite for code generation you need to install
``grpcio-tools`` using pip or some other mechanism::

  pip3 install --user grpcio-tools

To actually regenerate the code::

  ./setup.py build_grpc


Documenting
-----------
BuildStream starts out as a documented project from day one and uses
`sphinx <www.sphinx-doc.org>`_ to document itself.

This section discusses formatting policies for editing files in the
``doc/source`` directory, and describes the details of how the docs are
generated so that you can easily generate and view the docs yourself before
submitting patches to the documentation.

For details on how API documenting comments and docstrings are formatted,
refer to the :ref:`documenting section of the coding guidelines
<contributing_documenting_symbols>`.


Documentation formatting policy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The BuildStream documentation style is as follows:

* Titles and headings require two leading empty lines above them.
  Only the first word in a title should be capitalized.

  * If there is an ``.. _internal_link:`` anchor, there should be two empty lines
    above the anchor, followed by one leading empty line.

* Within a section, paragraphs should be separated by one empty line.

* Notes are defined using: ``.. note::`` blocks, followed by an empty line
  and then indented (3 spaces) text.

  * Other kinds of notes can be used throughout the documentation and will
    be decorated in different ways, these work in the same way as ``.. note::`` does.

    Feel free to also use ``.. attention::`` or ``.. important::`` to call special
    attention to a paragraph, ``.. tip::`` to give the reader a special tip on how
    to use an advanced feature or ``.. warning::`` to warn the user about a potential
    misuse of the API and explain its consequences.

* Code blocks are defined using: ``.. code:: LANGUAGE`` blocks, followed by an empty
  line and then indented (3 spaces) text. Note that the default language is ``python``.

* Cross references should be of the form ``:role:`target```.

  * Explicit anchors can be declared as ``.. _anchor_name:`` on a line by itself.

  * To cross reference arbitrary locations with, for example, the anchor ``anchor_name``,
    always provide some explicit text in the link instead of deriving the text from
    the target, e.g.: ``:ref:`Link text <anchor_name>```.
    Note that the "_" prefix is not used when referring to the target.

For further information about using the reStructuredText with sphinx, please see the
`Sphinx Documentation <http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_.


Building Docs
~~~~~~~~~~~~~
Before you can build the docs, you will end to ensure that you have installed
the required :ref:`buid dependencies <contributing_build_deps>` as mentioned
in the testing section above.

To build the documentation, just run the following::

  tox -e docs

This will give you a ``doc/build/html`` directory with the html docs which
you can view in your browser locally to test.


Regenerating session html
'''''''''''''''''''''''''
The documentation build will build the session files if they are missing,
or if explicitly asked to rebuild. We revision the generated session html files
in order to reduce the burden on documentation contributors.

To explicitly rebuild the session snapshot html files, it is recommended that you
first set the ``BST_SOURCE_CACHE`` environment variable to your source cache, this
will make the docs build reuse already downloaded sources::

  export BST_SOURCE_CACHE=~/.cache/buildstream/sources

To force rebuild session html while building the doc, simply run `tox` with the
``BST_FORCE_SESSION_REBUILD`` environment variable set, like so::

  env BST_FORCE_SESSION_REBUILD=1 tox -e docs


Man pages
~~~~~~~~~
Unfortunately it is quite difficult to integrate the man pages build
into the ``setup.py``, as such, whenever the frontend command line
interface changes, the static man pages should be regenerated and
committed with that.

To do this, first ensure you have ``click_man`` installed, possibly
with::

  pip3 install --user click_man

Then, in the toplevel directory of buildstream, run the following::

  python3 setup.py --command-packages=click_man.commands man_pages

And commit the result, ensuring that you have added anything in
the ``man/`` subdirectory, which will be automatically included
in the buildstream distribution.


User guide
~~~~~~~~~~
The :ref:`user guide <using>` is comprised of free form documentation
in manually written ``.rst`` files and is split up into a few sections,
of main interest are the :ref:`tutorial <tutorial>` and the
:ref:`examples <examples>`.

The distinction of the two categories of user guides is important to
understand too.

* **Tutorial**

  The tutorial is structured as a series of exercises which start with
  the most basic concepts and build upon the previous chapters in order
  to arrive at a basic understanding of how to create BuildStream projects.

  This series of examples should be easy enough to complete in a matter
  of a few hours for a new user, and should provide just enough insight to
  get the user started in creating their own projects.

  Going through the tutorial step by step should also result in the user
  becoming proficient enough with the reference manual to get by on their own.

* **Examples**

  These exist to demonstrate how to accomplish more advanced tasks which
  are not always obvious and discoverable.

  Alternatively, these also demonstrate elegant and recommended ways of
  accomplishing some tasks which could be done in various ways.


Guidelines
''''''''''
Here are some general guidelines for adding new free form documentation
to the user guide.

* **Focus on a single subject**

  It is important to stay focused on a single subject and avoid getting
  into tangential material when creating a new entry, so that the articles
  remain concise and the user is not distracted by unrelated subject material.

  A single tutorial chapter or example should not introduce any additional
  subject material than the material being added for the given example.

* **Reuse existing sample project elements**

  To help avoid distracting from the topic at hand, it is always preferable to
  reuse the same project sample material from other examples and only deviate
  slightly to demonstrate the new material, than to create completely new projects.

  This helps us remain focused on a single topic at a time, and reduces the amount
  of unrelated material the reader needs to learn in order to digest the new
  example.

* **Don't be redundant**

  When something has already been explained in the tutorial or in another example,
  it is best to simply refer to the other user guide entry in a new example.

  Always prefer to link to the tutorial if an explanation exists in the tutorial,
  rather than linking to another example, where possible.

* **Link into the reference manual at every opportunity**

  The format and plugin API is 100% documented at all times. Whenever discussing
  anything about the format or plugin API, always do so while providing a link
  into the more terse reference material.

  We don't want users to have to search for the material themselves, and we also
  want the user to become proficient at navigating the reference material over
  time.

* **Use concise terminology**

  As developers, we tend to come up with code names for features we develop, and
  then end up documenting a new feature in an example.

  Never use a code name or shorthand to refer to a feature in the user guide, instead
  always use fully qualified sentences outlining very explicitly what we are doing
  in the example, or what the example is for in the case of a title.

  We need to be considerate that the audience of our user guide is probably a
  proficient developer or integrator, but has no idea what we might have decided
  to name a given activity.


Structure of an example
'''''''''''''''''''''''
The :ref:`tutorial <tutorial>` and the :ref:`examples <examples>` sections
of the documentation contain a series of sample projects, each chapter in
the tutoral, or standalone example uses a sample project.

Here is the the structure for adding new examples and tutorial chapters.

* The example has a ``${name}``.

* The example has a project users can copy and use.

  * This project is added in the directory ``doc/examples/${name}``.

* The example has a documentation component.

  * This is added at ``doc/source/examples/${name}.rst``
  * An entry for ``examples/${name}`` is added to the toctree in ``doc/source/using_examples.rst``
  * This documentation discusses the project elements declared in the project and may
    provide some BuildStream command examples.
  * This documentation links out to the reference manual at every opportunity.

  .. note::

     In the case of a tutorial chapter, the ``.rst`` file is added in at
     ``doc/source/tutorial/${name}.rst`` and an entry for ``tutorial/${name}``
     is added to ``doc/source/using_tutorial.rst``.

* The example has a CI test component.

  * This is an integration test added at ``tests/examples/${name}``.
  * This test runs BuildStream in the ways described in the example
    and assert that we get the results which we advertize to users in
    the said examples.


Adding BuildStream command output
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
As a part of building the docs, BuildStream will run itself and extract
some html for the colorized output which is produced.

If you want to run BuildStream to produce some nice html for your
documentation, then you can do so by adding new ``.run`` files to the
``doc/sessions/`` directory.

Any files added as ``doc/sessions/${example}.run`` will result in generated
file at ``doc/source/sessions/${example}.html``, and these files can be
included in the reStructuredText documentation at any time with::

  .. raw:: html
     :file: sessions/${example}.html

The ``.run`` file format is just another YAML dictionary which consists of a
``commands`` list, instructing the program what to do command by command.

Each *command* is a dictionary, the members of which are listed here:

* ``directory``: The input file relative project directory.

* ``output``: The input file relative output html file to generate (optional).

* ``fake-output``: Don't really run the command, just pretend to and pretend
  this was the output, an empty string will enable this too.

* ``command``: The command to run, without the leading ``bst``.

* ``shell``: Specifying ``True`` indicates that ``command`` should be run as
  a shell command from the project directory, instead of a bst command (optional).

When adding a new ``.run`` file, one should normally also commit the new
resulting generated ``.html`` file(s) into the ``doc/source/sessions-stored/``
directory at the same time, this ensures that other developers do not need to
regenerate them locally in order to build the docs.

**Example**:

.. code:: yaml

   commands:

   # Make it fetch first
   - directory: ../examples/foo
     command: fetch hello.bst

   # Capture a build output
   - directory: ../examples/foo
     output: ../source/sessions/foo-build.html
     command: build hello.bst


.. _contributing_testing:

Testing
-------
BuildStream uses `tox <https://tox.readthedocs.org/>`_ as a frontend to run the
tests which are implemented using `pytest <https://pytest.org/>`_. We use
pytest for regression tests and testing out the behavior of newly added
components.

The elaborate documentation for pytest can be found here: http://doc.pytest.org/en/latest/contents.html

Don't get lost in the docs if you don't need to, follow existing examples instead.


.. _contributing_build_deps:

Installing build dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Some of BuildStream's dependencies have non-python build dependencies. When
running tests with ``tox``, you will first need to install these dependencies.
Exact steps to install these will depend on your oprtation systemm. Commands
for installing them for some common distributions are lised below.

For Fedora-based systems::

  dnf install gcc pkg-config python3-devel cairo-gobject-devel glib2-devel gobject-introspection-devel


For Debian-based systems::

  apt install gcc pkg-config python3-dev libcairo2-dev libgirepository1.0-dev


Running tests
~~~~~~~~~~~~~
To run the tests, simply navigate to the toplevel directory of your BuildStream
checkout and run::

  tox

By default, the test suite will be run against every supported python version
found on your host. If you have multiple python versions installed, you may
want to run tests against only one version and you can do that using the ``-e``
option when running tox::

  tox -e py37

Linting is performed separately from testing. In order to run the linting step which
consists of running the ``pycodestyle`` and ``pylint`` tools, run the following::

  tox -e lint

.. tip::

   The project specific pylint and pycodestyle configurations are stored in the
   toplevel buildstream directory in the ``.pylintrc`` file and ``setup.cfg`` files
   respectively. These configurations can be interesting to use with IDEs and
   other developer tooling.

The output of all failing tests will always be printed in the summary, but
if you want to observe the stdout and stderr generated by a passing test,
you can pass the ``-s`` option to pytest as such::

  tox -- -s

.. tip::

   The ``-s`` option is `a pytest option <https://docs.pytest.org/latest/usage.html>`_.

   Any options specified before the ``--`` separator are consumed by ``tox``,
   and any options after the ``--`` separator will be passed along to pytest.

You can always abort on the first failure by running::

  tox -- -x

If you want to run a specific test or a group of tests, you
can specify a prefix to match. E.g. if you want to run all of
the frontend tests you can do::

  tox -- tests/frontend/

Specific tests can be chosen by using the :: delimeter after the test module.
If you wanted to run the test_build_track test within frontend/buildtrack.py you could do::

  tox -- tests/frontend/buildtrack.py::test_build_track

We also have a set of slow integration tests that are disabled by
default - you will notice most of them marked with SKIP in the pytest
output. To run them, you can use::

  tox -- --integration

In case BuildStream's dependencies were updated since you last ran the
tests, you might see some errors like
``pytest: error: unrecognized arguments: --codestyle``. If this happens, you
will need to force ``tox`` to recreate the test environment(s). To do so, you
can run ``tox`` with ``-r`` or  ``--recreate`` option.

.. note::

   By default, we do not allow use of site packages in our ``tox``
   confguration to enable running the tests in an isolated environment.
   If you need to enable use of site packages for whatever reason, you can
   do so by passing the ``--sitepackages`` option to ``tox``. Also, you will
   not need to install any of the build dependencies mentioned above if you
   use this approach.

.. note::

   While using ``tox`` is practical for developers running tests in
   more predictable execution environments, it is still possible to
   execute the test suite against a specific installation environment
   using pytest directly::

     ./setup.py test

   Specific options can be passed to ``pytest`` using the ``--addopts``
   option::

     ./setup.py test --addopts 'tests/frontend/buildtrack.py::test_build_track'


Adding tests
~~~~~~~~~~~~
Tests are found in the tests subdirectory, inside of which
there is a separarate directory for each *domain* of tests.
All tests are collected as::

  tests/*/*.py

If the new test is not appropriate for the existing test domains,
then simply create a new directory for it under the tests subdirectory.

Various tests may include data files to test on, there are examples
of this in the existing tests. When adding data for a test, create
a subdirectory beside your test in which to store data.

When creating a test that needs data, use the datafiles extension
to decorate your test case (again, examples exist in the existing
tests for this), documentation on the datafiles extension can
be found here: https://pypi.python.org/pypi/pytest-datafiles.

Tests that run a sandbox should be decorated with::

  @pytest.mark.integration

and use the integration cli helper.

You must test your changes in an end-to-end fashion. Consider the first end to
be the appropriate user interface, and the other end to be the change you have
made.

The aim for our tests is to make assertions about how you impact and define the
outward user experience. You should be able to exercise all code paths via the
user interface, just as one can test the strength of rivets by sailing dozens
of ocean liners. Keep in mind that your ocean liners could be sailing properly
*because* of a malfunctioning rivet. End-to-end testing will warn you that
fixing the rivet will sink the ships.

The primary user interface is the cli, so that should be the first target 'end'
for testing. Most of the value of BuildStream comes from what you can achieve
with the cli.

We also have what we call a *"Public API Surface"*, as previously mentioned in
:ref:`contributing_documenting_symbols`. You should consider this a secondary
target. This is mainly for advanced users to implement their plugins against.

Note that both of these targets for testing are guaranteed to continue working
in the same way across versions. This means that tests written in terms of them
will be robust to large changes to the code. This important property means that
BuildStream developers can make large refactorings without needing to rewrite
fragile tests.

Another user to consider is the BuildStream developer, therefore internal API
surfaces are also targets for testing. For example the YAML loading code, and
the CasCache. Remember that these surfaces are still just a means to the end of
providing value through the cli and the *"Public API Surface"*.

It may be impractical to sufficiently examine some changes in an end-to-end
fashion. The number of cases to test, and the running time of each test, may be
too high. Such typically low-level things, e.g. parsers, may also be tested
with unit tests; alongside the mandatory end-to-end tests.

It is important to write unit tests that are not fragile, i.e. in such a way
that they do not break due to changes unrelated to what they are meant to test.
For example, if the test relies on a lot of BuildStream internals, a large
refactoring will likely require the test to be rewritten. Pure functions that
only rely on the Python Standard Library are excellent candidates for unit
testing.

Unit tests only make it easier to implement things correctly, end-to-end tests
make it easier to implement the right thing.


Measuring performance
---------------------


Benchmarking framework
~~~~~~~~~~~~~~~~~~~~~~~
BuildStream has a utility to measure performance which is available from a
separate repository at https://gitlab.com/BuildStream/benchmarks. This tool
allows you to run a fixed set of workloads with multiple versions of
BuildStream. From this you can see whether one version performs better or
worse than another which is useful when looking for regressions and when
testing potential optimizations.

For full documentation on how to use the benchmarking tool see the README in
the 'benchmarks' repository.


Profiling tools
~~~~~~~~~~~~~~~
When looking for ways to speed up the code you should make use of a profiling
tool.

Python provides `cProfile <https://docs.python.org/3/library/profile.html>`_
which gives you a list of all functions called during execution and how much
time was spent in each function. Here is an example of running ``bst --help``
under cProfile:

    python3 -m cProfile -o bst.cprofile -- $(which bst) --help

You can then analyze the results interactively using the 'pstats' module:

    python3 -m pstats ./bst.cprofile

For more detailed documentation of cProfile and 'pstats', see:
https://docs.python.org/3/library/profile.html.

For a richer visualisation of the callstack you can try `Pyflame
<https://github.com/uber/pyflame>`_. Once you have followed the instructions in
Pyflame's README to install the tool, you can profile `bst` commands as in the
following example:

    pyflame --output bst.flame --trace bst --help

You may see an `Unexpected ptrace(2) exception:` error. Note that the `bst`
operation will continue running in the background in this case, you will need
to wait for it to complete or kill it. Once this is done, rerun the above
command which appears to fix the issue.

Once you have output from pyflame, you can use the ``flamegraph.pl`` script
from the `Flamegraph project <https://github.com/brendangregg/FlameGraph>`_
to generate an .svg image:

    ./flamegraph.pl bst.flame > bst-flamegraph.svg

The generated SVG file can then be viewed in your preferred web browser.


Profiling specific parts of BuildStream with BST_PROFILE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BuildStream can also turn on cProfile for specific parts of execution
using BST_PROFILE.

BST_PROFILE can be set to a section name, or 'all' for all
sections. There is a list of topics in `buildstream/_profile.py`. For
example, running::

    BST_PROFILE=load-pipeline bst build bootstrap-system-x86.bst

will produce a profile in the current directory for the time take to
call most of `initialized`, for each element. These profile files
are in the same cProfile format as those mentioned in the previous
section, and can be analysed with `pstats` or `pyflame`.


Profiling the artifact cache receiver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Since the artifact cache receiver is not normally run directly, it's
necessary to alter the ForceCommand part of sshd_config to enable
profiling. See the main documentation in `doc/source/artifacts.rst`
for general information on setting up the artifact cache. It's also
useful to change directory to a logging directory before starting
`bst-artifact-receive` with profiling on.

This is an example of a ForceCommand section of sshd_config used to
obtain profiles::

    Match user artifacts
      ForceCommand BST_PROFILE=artifact-receive cd /tmp && bst-artifact-receive --pull-url https://example.com/ /home/artifacts/artifacts


Managing data files
-------------------
When adding data files which need to be discovered at runtime by BuildStream, update setup.py accordingly.

When adding data files for the purpose of docs or tests, or anything that is not covered by
setup.py, update the MANIFEST.in accordingly.

At any time, running the following command to create a source distribution should result in
creating a tarball which contains everything we want it to include::

  ./setup.py sdist


Updating BuildStream's Python dependencies
------------------------------------------
BuildStream's Python dependencies are listed in multiple
`requirements files <https://pip.readthedocs.io/en/latest/reference/pip_install/#requirements-file-format>`
present in the ``requirements`` directory.

All ``.txt`` files in this directory are generated from the corresponding
``.in`` file, and each ``.in`` file represents a set of dependencies. For
example, ``requirements.in`` contains all runtime dependencies of BuildStream.
``requirements.txt`` is generated from it, and contains pinned versions of all
runtime dependencies (including transitive dependencies) of BuildStream.

When adding a new dependency to BuildStream, or updating existing dependencies,
it is important to update the appropriate requirements file accordingly. After
changing the ``.in`` file, run the following to update the matching ``.txt``
file::

   make -C requirements
