project('buildstream', version: '0.1')

if get_option('check_backend') == 'auto'
  platform = host_machine.system()
  if platform == 'linux'
    backend = 'linux'
  else
    backend = 'posix'
  endif
else
  backend = get_option('check_backend')
endif

message('Checking dependencies for backend: @0@'.format(backend))


##################################################################
# Python requirements
##################################################################

python = find_program('python3', required: true)

python_version_check = run_command(python, '-c', 'import sys; sys.stdout.write("%d.%d" % (sys.version_info[0], sys.version_info[1]))')
if python_version_check.returncode() != 0
  error('Unable to detect Python version: ' + result.stdout() + result.stderr())
endif
python_version = python_version_check.stdout()

if not python_version.version_compare('>= 3.4')
  error('BuildStream requires Python >= 3.4')
endif

# FIXME: We check manually for our Python dependencies as Meson doesn't
# support doing so yet. See https://github.com/mesonbuild/meson/issues/2377
message('Checking for setuptools (for pkg_resources)')
setuptools_check = run_command(python, '-c', 'import pkg_resources')
if setuptools_check.returncode() != 0
  error('Python Setuptools was not found; the pkg_resources module is required.\n' +
        setuptools_check.stderr().strip())
endif

install_requires = [
  'blessings',
  'Click',
  'click-man',
  'jinja2',
  'pluginbase',
  'psutil',
  'ruamel.yaml',
]

setup_requires = [
  'setuptools_scm',
]

test_requires = [
  'pep8',
  # Pin coverage to 4.2 for now, we're experiencing
  # random crashes with 4.4.2
  'coverage == 4.4.0',
  'pytest >= 3.1.0',
  'pytest-cov',
  'pytest-datafiles',
  'pytest-env',
  'pytest-pep8',
  # Provide option to run tests in parallel, less reliable
  'pytest-xdist',
]

missing_dependency_errors = []

message('Checking for Python dependencies')
modules_check = run_command(python, 'meson-python-packages-check', install_requires + setup_requires + test_requires)
if modules_check.returncode() != 0
  error('Python dependency requirements are not satisfied:\n' + modules_check.stderr().strip())
endif

pytest = find_program('pytest-3')
# We configure pytest through a pytest.ini file in this directory, so as
# long as we set the workdir correctly it "just works" when run by Meson.
pytest_workdir = meson.current_source_dir()

##################################################################
# Bubblewrap requirements
##################################################################

if backend == 'linux'
  bwrap = find_program('bwrap', required: false)
  if not bwrap.found()
    error('Bubblewrap not found. BuildStream requires Bubblewrap (bwrap) for' +
          ' sandboxing the build environment. Install it using your package manager' +
          ' (usually bwrap or bubblewrap)')
  endif
endif


##################################################################
# OSTree version requirements
##################################################################

REQUIRED_OSTREE = '>= 2017.8'

if backend == 'linux'
  message('Checking for OSTree @0@ with PyGObject bindings'.format(REQUIRED_OSTREE))
  gi_check = run_command(python, '-c', 'import gi')
  if gi_check.returncode() != 0
    error('BuildStream requires PyGObject (aka PyGI). Install it using' +
          ' your package manager (usually pygobject3 or python-gi).')
  endif

  ostree_version_check = run_command('meson-ostree-check')
  if ostree_version_check.returncode() != 0
    message = ostree_version_check.stderr().strip()
    error(message + '\nBuildStream requires OSTree @0@ with Python bindings.'.format(REQUIRED_OSTREE) +
          ' Install it using your package manager (usually ostree or gir1.2-ostree-1.0).')
  else
    ostree_version = ostree_version_check.stdout().strip()
    if not ostree_version.version_compare(REQUIRED_OSTREE)
      error('OSTree is too old; found version @0@ but we require @1@'.format(ostree_version, REQUIRED_OSTREE))
    endif
  endif
endif


####################################################################
# bash-completion
####################################################################

install_bash_completion = false
if get_option('bash_completion') == 'yes' or get_option('bash_completion') == 'auto'
  bash_completion_package = dependency('bash-completion', required: false)
  if bash_completion_package.found()
    bash_completion_dir = bash_completion_package.get_pkgconfig_variable('completionsdir')
  else
    bash_completion_dir = join_paths(get_option('prefix'), get_option('datadir'), 'bash-completion', 'completions')
  endif
  install_bash_completion = true
elif get_option('bash_completion') == 'no' or get_option('bash_completion') == ''
  install_bash_completion = false
  bash_completion_dir = '(disabled)'
else
  install_bash_completion = true
  bash_completion_dir = get_option('bash_completion')
endif

if install_bash_completion
  message('Installing Bash completion script to @0@'.format(bash_completion_dir))
else
  message('Not installing Bash completion script')
endif


# Detect version from Git using setuptools_scm.
package_version_result = run_command(python, '-c', 'import setuptools_scm; print(setuptools_scm.get_version())')
if package_version_result.returncode() == 0
  package_version = package_version_result.stdout().strip()
  message('Detected package version from Git: @0@'.format(package_version))
else
  message('Failed to detect package version from Git: @0@.'.format(package_version_result.stderr().strip()))
  package_version = meson.project_version()
  message('Using version from Meson.build: @0@.'.format(package_version))
endif


python_name = 'python' + python_version
python_site_packages_dir = join_paths(get_option('prefix'), get_option('libdir'), python_name, 'site-packages')

cdata = configuration_data()
cdata.set('package_version', package_version)
cdata.set('pythondir', python_site_packages_dir)

subdir('buildstream')
subdir('man')
subdir('tests')
