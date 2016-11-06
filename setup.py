from setuptools import setup
from setuptools import find_packages

setup(name='buildstream',
      version='0.1',
      description='Framework for modelling of build pipelines in YAML',
      license='LGPL',
      packages=find_packages(),
      scripts=['bin/build-stream'],
      install_requires=[

          # Dependencies for the buildstream library
          'ruamel.yaml',
          'pluginbase',

          # Dependencies for the CLI frontend only
          'argparse'
      ],
      zip_safe=False)
