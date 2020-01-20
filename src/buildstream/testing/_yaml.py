import os

from buildstream._yaml import roundtrip_dump  # type: ignore


def generate_project(project_dir, config=None):
    if config is None:
        config = {}
    project_file = os.path.join(project_dir, "project.conf")
    if "name" not in config:
        config["name"] = os.path.basename(project_dir)
    roundtrip_dump(config, project_file)


def generate_element(element_dir, element_name, config=None):
    if config is None:
        config = {}
    element_path = os.path.join(element_dir, element_name)
    roundtrip_dump(config, element_path)
