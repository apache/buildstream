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

from ..node import Node


class MetaElement:

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
    def __init__(
        self,
        project,
        name,
        kind=None,
        provenance=None,
        sources=None,
        config=None,
        variables=None,
        environment=None,
        env_nocache=None,
        public=None,
        sandbox=None,
        first_pass=False,
    ):
        self.project = project
        self.name = name
        self.kind = kind
        self.provenance = provenance
        self.sources = sources
        self.config = config or Node.from_dict({})
        self.variables = variables or Node.from_dict({})
        self.environment = environment or Node.from_dict({})
        self.env_nocache = env_nocache or []
        self.public = public or Node.from_dict({})
        self.sandbox = sandbox or Node.from_dict({})
        self.build_dependencies = []
        self.dependencies = []
        self.strict_dependencies = []
        self.first_pass = first_pass
        self.is_junction = kind == "junction"
