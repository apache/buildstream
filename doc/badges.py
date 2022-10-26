#!/usr/bin/env python3
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#
import click
import subprocess
import re

# The badge template is modeled after the gitlab badge svgs
#
BADGE_TEMPLATE = """
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="116" height="20">
  <a xlink:href="{url_target}">
    <linearGradient id="{badge_name}_b" x2="0" y2="100%">
      <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
      <stop offset="1" stop-opacity=".1"/>
    </linearGradient>

    <mask id="{badge_name}_a">
      <rect width="116" height="20" rx="3" fill="#fff"/>
    </mask>

    <g mask="url(#{badge_name}_a)">
      <path fill="#555"
            d="M0 0 h62 v20 H0 z"/>
      <path fill="{color}"
            d="M62 0 h54 v20 H62 z"/>
      <path fill="url(#{badge_name}_b)"
            d="M0 0 h116 v20 H0 z"/>
    </g>

    <g fill="#fff" text-anchor="middle">
      <g font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="31" y="15" fill="#010101" fill-opacity=".3">
          {badge_name}
        </text>
        <text x="31" y="14">
          {badge_name}
        </text>
        <text x="89" y="15" fill="#010101" fill-opacity=".3">
          {version}
        </text>
        <text x="89" y="14">
          {version}
        </text>
      </g>
    </g>
  </a>
</svg>
"""

# The redirect template is for a static html page hosted in the
# latest docs which always redirects you to the latest snapshot
# or release on github.
#
REDIRECT_TEMPLATE = """
<!DOCTYPE html>
<html>
   <head>
      <title>Latest {badge_name}</title>
      <meta http-equiv="refresh" content="0;url={url_target}"/>
   </head>
   <body>
      <p></p>
   </body>
</html>
"""

URL_FORMAT = 'https://github.com/apache/buildstream/releases/tag/{version}'
RELEASE_COLOR = '#0040FF'
SNAPSHOT_COLOR = '#FF8000'
VERSION_TAG_MATCH = r'([0-9]*)\.([0-9]*)\.([0-9]*)'


# Parse a release tag and return a three tuple
# of the major, minor and micro version.
#
# Tags which do not follow the release tag format
# will just be returned as (0, 0, 0)
#
def parse_tag(tag):
    match = re.search(VERSION_TAG_MATCH, tag)
    if match:
        major = match.group(1)
        minor = match.group(2)
        micro = match.group(3)
        return (int(major), int(minor), int(micro))

    return (0, 0, 0)


# Call out to git and guess the latest version,
# this will just return (0, 0, 0) in case of any error.
#
def guess_version(release):
    try:
        tags_output = subprocess.check_output(['git', 'tag'])
    except subprocess.CalledProcessError:
        return (0, 0, 0)

    # Parse the `git tag` output into a list of integer tuples
    tags_output = tags_output.decode('UTF-8')
    all_tags = tags_output.splitlines()
    all_versions = [parse_tag(tag) for tag in all_tags]

    # Filter the list by the minor point version, if
    # we are checking for the latest "release" version, then
    # only pickup even number minor points.
    #
    filtered_versions = [
        version for version in all_versions
        if (version[1] % 2) == (not release)
    ]

    # Make sure they are sorted, and take the last one
    sorted_versions = sorted(filtered_versions)
    latest_version = sorted_versions[-1]

    return latest_version


@click.command(short_help="Generate the version badges")
@click.option('--release', is_flag=True, default=False,
              help="Whether to generate the badge for the release version")
@click.option('--redirect', is_flag=True, default=False,
              help="Whether to generate the redirect html file")
def generate_badges(release, redirect):
    """Generate the version badge svg files
    """
    major, minor, micro = guess_version(release)

    if release:
        badge_name = 'release'
        color = RELEASE_COLOR
    else:
        badge_name = 'snapshot'
        color = SNAPSHOT_COLOR

    version = '{major}.{minor}.{micro}'.format(major=major, minor=minor, micro=micro)
    url_target = URL_FORMAT.format(version=version)

    if redirect:
        template = REDIRECT_TEMPLATE
    else:
        template = BADGE_TEMPLATE

    output = template.format(badge_name=badge_name,
                             version=version,
                             color=color,
                             url_target=url_target)

    click.echo(output, nl=False)
    return 0


if __name__ == '__main__':
    generate_badges()
