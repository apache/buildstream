import os
import re
import shutil
import subprocess
import sys

import pytest


SETUP_TEMPLATE = """\
from setuptools import setup

setup(
    name='{name}',
    version='{version}',
    description='{name}',
    packages=['{pkgdirname}'],
    install_requires={pkgdeps},
    entry_points={{
        'console_scripts': [
            '{pkgdirname}={pkgdirname}:main'
        ]
    }}
)
"""

# All packages generated via generate_pip_package will have the functions below
INIT_TEMPLATE = """\
def main():
    print('This is {name}')

def hello(actor='world'):
    print('Hello {{}}! This is {name}'.format(actor))
"""

HTML_TEMPLATE = """\
<html>
  <head>
    <title>Links for {name}</title>
  </head>
  <body>
    <a href='{name}-{version}.tar.gz'>{name}-{version}.tar.gz</a><br />
  </body>
</html>
"""


# Creates a simple python source distribution and copies this into a specified
# directory which is to serve as a mock python repository
#
# Args:
#    tmpdir (str): Directory in which the source files will be created
#    pypi (str): Directory serving as a mock python repository
#    name (str): The name of the package to be created
#    version (str): The version of the package to be created
#
# Returns:
#    None
#
def generate_pip_package(tmpdir, pypi, name, version="0.1", dependencies=None):
    if dependencies is None:
        dependencies = []
    # check if package already exists in pypi
    pypi_package = os.path.join(pypi, re.sub("[^0-9a-zA-Z]+", "-", name))
    if os.path.exists(pypi_package):
        return

    # create the package source files in tmpdir resulting in a directory
    # tree resembling the following structure:
    #
    # tmpdir
    # |-- setup.py
    # `-- package
    #     `-- __init__.py
    #
    setup_file = os.path.join(tmpdir, "setup.py")
    pkgdirname = re.sub("[^0-9a-zA-Z]+", "", name)
    with open(setup_file, "w") as f:
        f.write(SETUP_TEMPLATE.format(name=name, version=version, pkgdirname=pkgdirname, pkgdeps=dependencies))
    os.chmod(setup_file, 0o755)

    package = os.path.join(tmpdir, pkgdirname)
    os.makedirs(package)

    main_file = os.path.join(package, "__init__.py")
    with open(main_file, "w") as f:
        f.write(INIT_TEMPLATE.format(name=name))
    os.chmod(main_file, 0o644)

    # Run sdist with a fresh process
    subprocess.run([sys.executable, "setup.py", "sdist"], cwd=tmpdir, check=True)

    # create directory for this package in pypi resulting in a directory
    # tree resembling the following structure:
    #
    # pypi
    # `-- pypi_package
    #     |-- index.html
    #     `-- foo-0.1.tar.gz
    #
    os.makedirs(pypi_package)

    # add an index html page
    index_html = os.path.join(pypi_package, "index.html")
    with open(index_html, "w") as f:
        f.write(HTML_TEMPLATE.format(name=name, version=version))

    # copy generated tarfile to pypi package
    dist_dir = os.path.join(tmpdir, "dist")
    for tar in os.listdir(dist_dir):
        tarpath = os.path.join(dist_dir, tar)
        shutil.copy(tarpath, pypi_package)


@pytest.fixture
def setup_pypi_repo(tmpdir):
    def create_pkgdir(package):
        pkgdirname = re.sub("[^0-9a-zA-Z]+", "", package)
        pkgdir = os.path.join(str(tmpdir), pkgdirname)
        os.makedirs(pkgdir)
        return pkgdir

    def add_packages(packages, pypi_repo):
        for package, dependencies in packages.items():
            pkgdir = create_pkgdir(package)
            generate_pip_package(pkgdir, pypi_repo, package, dependencies=list(dependencies.keys()))
            for dependency, dependency_dependencies in dependencies.items():
                add_packages({dependency: dependency_dependencies}, pypi_repo)

    return add_packages
