#!/usr/bin/env python3

from enum import Enum
from ruamel import yaml


class PluginVersion(Enum):
    MASTER = 0
    FIXED = 1


def load_file(filename):
    with open(filename, 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)


def format_single_req(dep, version):
    extras = ''
    if 'extras' in dep.keys():
        extras = ','.join(dep['extras'])

    if version == PluginVersion.MASTER:
        ref = 'master'
        if 'branch' in dep.keys():
            ref = dep['branch']
    else:
        ref = dep['tag']

    return "git+{}@{}#egg={}[{}]\n".format(
        dep['url'],
        ref,
        dep['package_name'],
        extras)


def write_requirements_file(filename, deps, version):
    with open(filename, 'w') as f:
        for dep in deps:
            f.write(format_single_req(dep, version))


if __name__ == '__main__':
    deps = load_file('requirements/external-requirements.yml')

    write_requirements_file('requirements/external-master.txt', deps, PluginVersion.MASTER)
    write_requirements_file('requirements/external-fixed.txt', deps, PluginVersion.FIXED)
