
try:
    from setuptools import setup, find_packages
except ImportError:
    print("BuildStream requires setuptools in order to build. Install it using"
          " your package manager (usually python3-setuptools) or via pip (pip3"
          " install setuptools).")
    sys.exit(1)

setup(name='buildstream',
      version='0.1',
      description='Framework for modelling of build pipelines in YAML',
      license='LGPL',
      packages=find_packages(),
      package_data={'buildstream': ['plugins/*/*.py']},
      scripts=['bin/build-stream'],
      install_requires=[

          # Dependencies for the buildstream library
          'ruamel.yaml',
          'pluginbase',

          # Dependencies for the CLI frontend only
          'argparse'
      ],
      zip_safe=False)
