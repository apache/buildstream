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

Contributing to the UI
~~~~~~~~~~~~~~~~~~~~~~

As we wish to cleanly separate BuildStream's core from the frontend, anything
user facing should be defined within the modules contained within the `_frontend
<https://github.com/apache/buildstream/tree/master/src/buildstream/_frontend>`_
directory.

BuildStream's frontend includes:

    * Implementation of the command line interface (cli.py)
    * Logline/text formatting (widget.py)
    * The main application state (app.py) which initializes the stream to handle
      logging and user interactions.
    * Colour profiles (profile.py)
    * Rendering of the status bar (status.py)
    * Autocompletion behaviour (completions.py)


The command line interface
''''''''''''''''''''''''''
All of BuildStream's commands are defined within the module `cli.py
<https://github.com/apache/buildstream/tree/master/src/buildstream/_frontend/cli.py>`_ -,
the main entry point which implements the CLI.

The command line interface is generated with `Click
<https://palletsprojects.com/p/click/>`_ - a third party Python package. Click
is easy to use and automatically generates help pages.

When working with commands, please adhere to the following checklist:

1. All commands should be defined with a help text
2. The command should be placed within the appropriate sub group

   - If the command manipulates sources, it should be part of the
     :ref:`source_subcommands`.
   - If the command manipulates cached artifacts, it should be part of the
     :ref:`artifact_subcommands`.
   - If the command has anything to do with workspaces, it should be part
     of the :ref:`workspace_subcommands`.

3. If the command is intended to work with artifact refs as well as element
   names, the command's argument should be "artifacts" as this supports the
   auto-completion of artifact refs.
4. The supported `--deps` options are: "run", "build", "all", "plan" and "none".
   These are always of type `click.Choice
   <https://click.palletsprojects.com/en/7.x/options/#choice-options>`_ and
   should always be specified with a default. If the default is "none", note that
   we use the string "none", not the Python built-in ``None``. In addition to this,
   the ``show_default`` flag should be set to ``True``.
5. Commands should use the app and go through the stream (via a similarly named
   method within Stream) in order to communicate to BuildStream's core.


Displaying information
''''''''''''''''''''''

Output which we wish to display to the user from the frontend should use the
implemented classes in widget.py. This module contains classes which represent
widgets for displaying information to the user.

To report messages back to the frontend, we use the ``Message()`` object
which is available from the ``Context``.

Supported message types are defined in `_message.py
<https://github.com/apache/buildstream/tree/master/src/buildstream/_message.py>`_
and various uses of the messenger are defined in `_messenger.py
<https://github.com/apache/buildstream/tree/master/src/buildstream/_messenger.py>`_

The ``Messenger`` class defines various methods which allow us to report back to
the frontend in particular ways. The common methods are:

* ``Messenger.message()`` - the central point through which all messages pass
* ``Messenger.timed_activity()`` - a context manager for performing and logging
  timed activities.
* ``Messenger.simple_task()`` - a Context manager for creating a task to report
  progress too.
