import os
from buildstream import _yaml


# Shared function to configure the project.conf inline
#
def configure_project(path, config):
    config['name'] = 'test'
    config['element-path'] = 'elements'
    _yaml.dump(config, os.path.join(path, 'project.conf'))
