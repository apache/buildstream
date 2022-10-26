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

from setuptools import setup, find_packages

setup(
    name="sample-plugins",
    version="1.2.3",
    description="A collection of sample plugins for testing.",
    license="Apache License Version 2.0",
    url="https://example.com/sample-plugins",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    entry_points={
        "buildstream.plugins.elements": [
            "sample = sample_plugins.elements.sample",
            "autotools = sample_plugins.elements.autotools",
        ],
        "buildstream.plugins.sources": [
            "sample = sample_plugins.sources.sample",
            "git = sample_plugins.sources.git",
        ],
    },
    zip_safe=False,
)
# eof setup()
