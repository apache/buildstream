#!/usr/bin/env python3
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

import os
import sys
import click
import pkg_resources  # From setuptools

from . import Context, Project
from . import LoadError, SourceError, ElementError
from ._pipeline import Pipeline

# Some nasty globals
build_stream_version = pkg_resources.require("buildstream")[0].version
_, _, _, _, host_machine = os.uname()

main_options = {}


def create_pipeline(directory, target, arch, variant, config):

    try:
        context = Context(arch)
        context.load(config)
    except LoadError as e:
        click.echo("Error loading user configuration: %s" % str(e))
        sys.exit(1)

    try:
        project = Project(directory)
    except LoadError as e:
        click.echo("Error loading project: %s" % str(e))
        sys.exit(1)

    try:
        pipeline = Pipeline(context, project, target, variant)
    except (LoadError, PluginError, SourceError, ElementError, ProgramNotFoundError) as e:
        click.echo("Error loading pipeline: %s" % str(e))
        sys.exit(1)

    return pipeline


##################################################################
#                          Main Options                          #
##################################################################
@click.group()
@click.version_option(version=build_stream_version)
@click.option('--config', '-c',
              type=click.Path(exists=True, dir_okay=False, readable=True),
              help="Configuration file to use")
@click.option('--verbose', '-v', default=False, is_flag=True,
              help="Whether to be extra verbose")
@click.option('--directory', '-C', default=os.getcwd(),
              type=click.Path(exists=True, file_okay=False, readable=True),
              help="Project directory (default: %s)" % os.getcwd())
def cli(config, verbose, directory):
    """Build and manipulate BuildStream projects"""
    main_options['config'] = config
    main_options['verbose'] = verbose
    main_options['directory'] = directory


##################################################################
#                         Refresh Command                        #
##################################################################
@cli.command(short_help="Refresh sources in a pipeline")
@click.option('--arch', '-a', default=host_machine,
              help="The target architecture (default: %s)" % host_machine)
@click.option('--variant',
              help='A variant of the specified target')
@click.option('--list', '-l', default=False, is_flag=True,
              help='List the sources which were refreshed')
@click.argument('target')
def refresh(target, arch, variant, list):
    """Refresh sources in a pipeline

    Updates the project with new source references from
    any sources which are configured to track a remote
    branch or tag.
    """
    pipeline = create_pipeline(main_options['directory'], target, arch, variant, main_options['config'])

    try:
        sources = pipeline.refresh()
    except (SourceError, ElementError) as e:
        click.echo("Error refreshing pipeline: %s" % str(e))
        sys.exit(1)

    if list:
        # --list output
        for source in sources:
            click.echo("{}".format(source))

    elif len(sources) > 0:
        click.echo(("Successfully refreshed {n_sources} sources in pipeline " +
                    "with target '{target}' in directory: {directory}").format(
                        n_sources=len(sources), target=target, directory=main_options['directory']))
    else:
        click.echo(("Pipeline with target '{target}' already up to date in directory: {directory}").format(
            target=target, directory=main_options['directory']))
