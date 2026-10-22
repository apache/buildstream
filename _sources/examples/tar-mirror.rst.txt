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



.. _using_tar_mirror:

Creating and using a tar mirror
'''''''''''''''''''''''''''''''
This is an example of how to create a tar mirror using 
`lighttpd <https://redmine.lighttpd.net/projects/1/wiki/TutorialConfiguration>`_.


Prerequisites
=============
You will need `lighttpd` installed.


I will be using gnome-modulesets as an example, which can be cloned from
`http://gnome7.codethink.co.uk/gnome-modulesets.git`.


Starting a tar server
=====================


1. Set up a directory containing mirrors
----------------------------------------
Choose a suitable directory to hold your mirrored tar files, e.g. `/var/www/tar`.

Place the tar files you want to use as mirrors in your mirror dir, e.g.

.. code::

   mkdir -p /var/www/tar/gettext
   wget -O /var/www/tar/gettext/gettext-0.19.8.1.tar.xz https://ftp.gnu.org/gnu/gettext/gettext-0.19.8.1.tar.xz


2. Configure lighttpd
---------------------
Write out a lighttpd.conf as follows:

::

   server.document-root = "/var/www/tar/" 
   server.port = 3000
   
   dir-listing.activate = "enable"

.. note::

   If you have your mirrors in another directory, replace /var/www/tar/ with that directory.

.. note::

   An example lighttpd.conf that works for both git and tar services is available
   :ref:`here <lighttpd_git_tar_conf>`


3. Start lighttpd
-----------------
lighttpd can be invoked with the command-line ``lighttpd -D -f lighttpd.conf``.


4. Test that you can fetch from it
----------------------------------
We can then download the mirrored file with ``wget 127.0.0.1:3000/tar/gettext/gettext-0.19.8.1.tar.xz``.

.. note::

   If you have set server.port to something other than the default, you will need
   to replace the '3000' in the command-line.


5. Configure the project to use the mirror
------------------------------------------
To add this local http server as a mirror, add the following to the project.conf:

.. code:: yaml

   mirrors:
   - name: local-mirror
     aliases:
       ftp_gnu_org:
       - http://127.0.0.1:3000/tar/


6. Test that the mirror works
-----------------------------
We can make buildstream use the mirror by setting the alias to an invalid URL, e.g.

.. code:: yaml

   aliases:
     ftp_gnu_org: https://www.example.com/invalid/url/

Now, if you build an element that uses the source you placed in the mirror
(e.g. ``bst build core-deps/gettext.bst``), you will see that it uses your mirror.


Further reading
===============
If this mirror isn't being used exclusively in a secure network, it is strongly
recommended you `use SSL <https://redmine.lighttpd.net/projects/1/wiki/HowToSimpleSSL>`_.

Lighttpd is documented on `its wiki <https://redmine.lighttpd.net/projects/lighttpd/wiki>`_.
