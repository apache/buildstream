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


python_name = 'python' + python_version
python_site_packages_dir = join_paths(get_option('prefix'), get_option('libdir'), python_name, 'site-packages')

cdata = configuration_data()
cdata.set('pythondir', python_site_packages_dir)

subdir('buildstream')
