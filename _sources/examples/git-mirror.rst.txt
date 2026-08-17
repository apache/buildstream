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



Creating and using a git mirror
'''''''''''''''''''''''''''''''
This is an example of how to create a git mirror using git's
`git-http-backend <https://git-scm.com/docs/git-http-backend>`_ and
`lighttpd <https://redmine.lighttpd.net/projects/1/wiki/TutorialConfiguration>`_.


Prerequisites
=============
You will need git installed, and git-http-backend must be present. It is assumed
that the git-http-backend binary exists at `/usr/lib/git-core/git-http-backend`.

You will need `lighttpd` installed, and at the bare minimum has the modules
`mod_alias`, `mod_cgi`, and `mod_setenv`.

I will be using gnome-modulesets as an example, which can be cloned from
`http://gnome7.codethink.co.uk/gnome-modulesets.git`.


Starting a git http server
==========================


1. Set up a directory containing mirrors
----------------------------------------
Choose a suitable directory to hold your mirrors, e.g. `/var/www/git`.

Place the git repositories you want to use as mirrors in the mirror dir, e.g.
``git clone --mirror http://git.gnome.org/browse/yelp-xsl /var/www/git/yelp-xsl.git``.


2. Configure lighttpd
---------------------
Write out a lighttpd.conf as follows:

::

   server.document-root = "/var/www/git/" 
   server.port = 3000
   server.modules = (
        "mod_alias",
        "mod_cgi",
        "mod_setenv",
   )
   
   alias.url += ( "/git" => "/usr/lib/git-core/git-http-backend" )
   $HTTP["url"] =~ "^/git" {
        cgi.assign = ("" => "")
        setenv.add-environment = (
                "GIT_PROJECT_ROOT" => "/var/www/git",
                "GIT_HTTP_EXPORT_ALL" => ""
        )
   }

.. note::

   If you have your mirrors in another directory, replace /var/www/git/ with that directory.


3. Start lighttpd
-----------------
lighttpd can be invoked with the command-line ``lighttpd -D -f lighttpd.conf``.


4. Test that you can fetch from it
----------------------------------
We can then clone the mirrored repo using git via http with
``git clone http://127.0.0.1:3000/git/yelp-xsl``.

.. note::

   If you have set server.port to something other than the default, you will
   need to replace the '3000' in the command-line.


5. Configure the project to use the mirror
------------------------------------------
To add this local http server as a mirror, add the following to the project.conf:

.. code:: yaml

   mirrors:
   - name: local-mirror
     aliases:
       git_gnome_org:
       - http://127.0.0.1:3000/git/


6. Test that the mirror works
-----------------------------
We can make buildstream use the mirror by setting the alias to an invalid URL, e.g.

.. code:: yaml

   aliases:
     git_gnome_org: https://www.example.com/invalid/url/

Now, if you build an element that uses the source you placed in the mirror
(e.g. ``bst build core-deps/yelp-xsl.bst``), you will see that it uses your mirror.


.. _lighttpd_git_tar_conf:

Bonus: lighttpd conf for git and tar
====================================
For those who have also used the :ref:`tar-mirror tutorial <using_tar_mirror>`,
a combined lighttpd.conf is below:

::

   server.document-root = "/var/www/"
   server.port = 3000
   server.modules = (
           "mod_alias",
           "mod_cgi",
           "mod_setenv",
   )
   
   alias.url += ( "/git" => "/usr/lib/git-core/git-http-backend" )
   $HTTP["url"] =~ "^/git" {
           cgi.assign = ("" => "")
           setenv.add-environment = (
                   "GIT_PROJECT_ROOT" => "/var/www/git",
                   "GIT_HTTP_EXPORT_ALL" => ""
           )
   } else $HTTP["url"] =~ "^/tar" {
           dir-listing.activate = "enable"
   }


Further reading
===============
If this mirror isn't being used exclusively in a secure network, it is strongly
recommended you `use SSL <https://redmine.lighttpd.net/projects/1/wiki/HowToSimpleSSL>`_.

This is the bare minimum required to set up a git mirror. A large, public project
would prefer to set it up using the
`git protocol <https://git-scm.com/book/en/v1/Git-on-the-Server-Git-Daemon>`_,
and a security-conscious project would be configured to use
`git over SSH <https://git-scm.com/book/en/v1/Git-on-the-Server-Getting-Git-on-a-Server#Small-Setups>`_.

Lighttpd is documented on `its wiki <https://redmine.lighttpd.net/projects/lighttpd/wiki>`_.
