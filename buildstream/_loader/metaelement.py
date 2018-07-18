#
#  Copyright (C) 2016 Codethink Limited
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


class MetaElement():

    # MetaElement()
    #
    # An abstract object holding data suitable for constructing an Element
    #
    # Args:
    #    project: The project that contains the element
    #    name: The resolved element name
    #    kind: The element kind
    #    provenance: The provenance of the element
    #    sources: An array of MetaSource objects
    #    config: The configuration data for the element
    #    variables: The variables declared or overridden on this element
    #    environment: The environment variables declared or overridden on this element
    #    env_nocache: List of environment vars which should not be considered in cache keys
    #    public: Public domain data dictionary
    #    sandbox: Configuration specific to the sandbox environment
    #    first_pass: The element is to be loaded with first pass configuration (junction)
    #
    def __init__(self, project, name, kind, provenance, sources, config,
                 variables, environment, env_nocache, public, sandbox,
                 first_pass):
        self.project = project
        self.name = name
        self.kind = kind
        self.provenance = provenance
        self.sources = sources
        self.config = config
        self.variables = variables
        self.environment = environment
        self.env_nocache = env_nocache
        self.public = public
        self.sandbox = sandbox
        self.build_dependencies = []
        self.dependencies = []
        self.first_pass = first_pass
