import os

from buildstream import _yaml
from .junction import generate_junction


def configure_project(path, config):
    config['name'] = 'test'
    config['element-path'] = 'elements'
    _yaml.roundtrip_dump(config, os.path.join(path, 'project.conf'))
