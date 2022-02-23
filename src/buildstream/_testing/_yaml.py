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
