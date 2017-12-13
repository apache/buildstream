subdir('_artifactcache')
subdir('data')
subdir('_frontend')
subdir('_fuse')
subdir('_options')
subdir('_platform')
subdir('plugins/elements')
subdir('plugins/sources')
subdir('sandbox')
subdir('_scheduler')

sources = [
    '__init__.py',
    'buildelement.py',
    '_context.py',
    '_elementfactory.py',
    'element.py',
    '_exceptions.py',
    '_loader.py',
    '_message.py',
    '_metaelement.py',
    '_metasource.py',
    '_ostree.py',
    '_pipeline.py',
    '_plugincontext.py',
    'plugin.py',
    '_profile.py',
    '_project.py',
    'scriptelement.py',
    '_signals.py',
    '_site.py',
    '_sourcefactory.py',
    'source.py',
    'utils.py',
    '_variables.py',
    '_yaml.py',
]

main = configure_file(
    input: 'main.py.in',
    output: 'bst',
    configuration: cdata,
    install_dir: get_option('bindir'))

install_data(
    sources,
    install_dir: join_paths(python_site_packages_dir, 'buildstream'))
