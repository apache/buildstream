Running on Windows
==================

This is a temporary doc tied to the lifetime of the `aevri/win32` branch,
intended to help you repro the results.

Installation
------------

First, make sure you have Python 3 installed.

Next, you probably want to create a venv to install BuildStream into, for
experimentation.

Then, clone and install BuildStream:

    git clone  --branch aevri/win32 https://gitlab.com/buildstream/buildstream.git
    pip install -e ./buildstream

Next, install some additional dependencies for proper display:

    pip install colorama windows-curses

Finally, make sure you have the build tools installed:

- Download the installer from: https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2017
- Run the installer.
- Select to install "Visual C++ build tools". Possibly need to include these
  optional items:
    - Windows 10 SDK
    - Visual C++ tools for CMake
    - Testing tools core feature - Build Tools

Hello World
-----------

Here is how to build the "Hello World" example.

First, launch a "Developer Command Prompt for VS 2017". This ensures that you
have the correct environment variables for building. The next instructions
assume you are running inside this prompt.

Next, make sure you have activated any virtual environment for BuildStream.

Then, change directory to the buildstream git repository.

Finally, build and run like so:

    bst --help

    cd doc\examples\running-commands

    bst show hello.bst

    bst build hello.bst

    bst artifact checkout hello.bst --directory checkout
    cd checkout
    hello.exe
