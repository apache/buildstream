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
import os
from buildstream import _yaml


def load_yaml(filename):
    return _yaml.load(filename, shortname=os.path.basename(filename))


def generate_project(project_dir, config=None):
    if config is None:
        config = {}
    project_file = os.path.join(project_dir, "project.conf")
    if "name" not in config:
        config["name"] = os.path.basename(project_dir)
    if "min-version" not in config:
        config["min-version"] = "2.0"
    _yaml.roundtrip_dump(config, project_file)


def generate_element(element_dir, element_name, config=None):
    if config is None:
        config = {}
    element_path = os.path.join(element_dir, element_name)
    _yaml.roundtrip_dump(config, element_path)
