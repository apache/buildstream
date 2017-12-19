data = [
    'build-all.sh.in',
    'build-module.sh.in',
    'projectconfig.yaml',
    'userconfig.yaml',
]

install_data(data,
    install_dir: join_paths(python_site_packages_dir, 'buildstream', 'data'))

if install_bash_completion
  install_data('bst',
    install_dir: bash_completion_dir)
endif
