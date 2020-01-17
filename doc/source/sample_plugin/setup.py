from setuptools import setup, find_packages

setup(name='BuildStream Autotools',
      version="0.1",
      description="A better autotools element for BuildStream",
      packages=find_packages(),
      include_package_data=True,
      entry_points={
          'buildstream.plugins.elements': [
              'autotools = elements.autotools'
          ]
      })
