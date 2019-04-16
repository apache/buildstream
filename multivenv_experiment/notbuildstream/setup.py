from setuptools import setup

setup(
    name="notbuildstream",
    version="0.1",
    py_modules=["notbuildstream"],
    install_requires=["Click", "pluginbase"],
    entry_points="""
        [console_scripts]
        notbst=notbuildstream:cli
    """,
)
