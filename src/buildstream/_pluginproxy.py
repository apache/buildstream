#
#  Copyright (C) 2020 Codethink Limited
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

from .plugin import Plugin


# PluginProxyError()
#
# The PluginProxyError is raised by PluginProxy objects when an illegal
# method call is called by a Plugin.
#
# This exception does not derive from BstError because it is not a user
# facing error but a Plugin author facing error; the result of a
# PluginProxyError being raised is that BuildStream treats it as an
# unhandled exception, and issues a BUG message with a helpful stacktrace
# which can be helpful for the Plugin author to fix their bugs.
#
class PluginProxyError(Exception):
    pass


# PluginProxy()
#
# Base class for proxies to Plugin instances.
#
# Proxies are handed off to Plugin implementations whenever they observe the data
# model, like when the Element observes it's dependencies, this allows the core to
# do some police work and raise errors when plugins attempt to perform illegal method
# calls.
#
# Refer to the Plugin class for the documentation for these APIs.
#
# In this file we simply raise a PluginProxyError() in the case that a Plugin tries to
# call an illegal API, or we forward the method call along to the underlying Plugin
# instance if the given method call is considered legal.
#
# Args:
#    owner (Plugin): The owning plugin, i.e. the plugin which this proxy was given to
#    plugin (Plugin): The proxied plugin, i.e. the plugin this proxy is attached to
#
class PluginProxy:
    def __init__(self, owner: Plugin, plugin: Plugin):

        # These members are considered internal, they are accessed by subclasses
        # which extend the PluginProxy, but hidden from the client Plugin implementations
        # which the proxy objects are handed off to.
        #
        self._owner = owner  # The Plugin this proxy was given to / created for
        self._plugin = plugin  # The Plugin this proxy was created as a proxy for

    # We use the fallback __getattr__ method to trigger plugin author facing
    # errors for any methods we have not explicitly redirected to the underlying
    # plugin object.
    #
    def __getattr__(self, name):
        if hasattr(self._plugin, name):
            raise PluginProxyError(
                "{}: Illegal attempt to access attribute '{}' on plugin: {}".format(self._owner, name, self._plugin)
            )
        raise AttributeError("{}: Has no attribute '{}'".format(self._plugin, name))

    ##############################################################
    #                   Exposed proxied APIs                     #
    ##############################################################
    @property
    def name(self):
        return self._plugin.name

    def get_kind(self) -> str:
        return self._plugin.get_kind()

    @property
    def _unique_id(self):
        return self._plugin._unique_id
