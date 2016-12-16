# Copyright (C) 2015  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.


'''Test programs for testing sandbox. Originally from 'sandboxlib'

---

Test programs for 'sandboxlib' functional tests.

The tests need to create clean, reproducible sandboxes in order for the tests
to behave the same on all machines. This means not depending on the host OS.
We need some programs to actually run inside the sandbox and try to break them.
There are two approaches: either build / download a small OS from somewhere
that will run in a chroot and will work the same on all platforms, or build
minimal, self-contained tester programs using tools in the host OS.

I picked the second approach: to test the sandboxes using statically linked C
programs. Each C program below should be simple, portable, self-contained and
should test one thing.

'''


import py
import pytest

import subprocess
import tempfile


def build_c_program(source_code, output_path, compiler_args=None):
    '''Compile a temporary C program.

    This assumes that the host system has 'cc' available.

    '''
    compiler_args = compiler_args or []
    with tempfile.NamedTemporaryFile(suffix='.c') as f:
        f.write(source_code.encode('utf-8'))
        f.flush()

        process = subprocess.Popen(
            ['cc', '-static', f.name, '-o', str(output_path)],
            stderr=subprocess.PIPE)
        process.wait()
        if process.returncode != 0:
            pytest.fail(
                "Unable to compile test C program: %s" % process.stderr.read())


@pytest.fixture(scope='session')
def session_tmpdir(request):
    '''Workaround for a limitation of the py.test 'tmpdir' fixture.

    See: <https://stackoverflow.com/questions/25525202/>

    '''
    dir = py.path.local(tempfile.mkdtemp())
    request.addfinalizer(lambda: dir.remove(rec=1))
    # Any extra setup here
    return dir


FILE_OR_DIRECTORY_EXISTS_TEST_PROGRAM = """
#include <stdio.h>
#include <sys/stat.h>

int main(int argc, char *argv[]) {
    struct stat stat_data;

    if (argc != 2) {
        fprintf(stderr, "Expected 1 argument: filename to try to read from.");
        return 2;
    }

    if (stat(argv[1], &stat_data) != 0) {
        printf("Did not find %s.", argv[1]);
        return 1;
    }

    printf("%s exists", argv[1]);
    return 0;
};
"""


@pytest.fixture(scope='session')
def file_or_directory_exists_test_program(session_tmpdir):
    '''Returns the path to a program that tests if a file or directory exists.

    The program takes a path on the commandline, and returns 0 if the path
    points to an existing file or directory, 1 if it doesn't exist, or 2 on
    error.

    '''
    program_path = session_tmpdir.join('test-file-or-directory-exists')
    build_c_program(
        FILE_OR_DIRECTORY_EXISTS_TEST_PROGRAM, program_path,
        compiler_args=['-static'])
    return program_path


FILE_IS_WRITABLE_TEST_PROGRAM = """
#include <stdio.h>

int main(int argc, char *argv[]) {
    FILE *file;

    if (argc != 2) {
        fprintf(stderr, "Expected 1 argument: filename to try to write to.");
        return 2;
    }

    file = fopen(argv[1], "w");

    if (file == NULL) {
        printf("Couldn't open %s for writing.", argv[1]);
        return 1;
    }

    if (fputc('!', file) != '!') {
        printf("Couldn't write to %s.", argv[1]);
        fclose(file);
        return 1;
    }

    fclose(file);
    printf("Wrote data to %s.", argv[1]);
    return 0;
};
"""


@pytest.fixture(scope='session')
def file_is_writable_test_program(session_tmpdir):
    '''Returns the path to a program that test if a file is writable.

    The program takes a path on the commandline, and return 0 if the given
    path is a file that can be written to, 2 if the given path cannot be
    written to, or 2 on error.

    '''
    program_path = session_tmpdir.join('test-file-is-writable')
    build_c_program(
        FILE_IS_WRITABLE_TEST_PROGRAM, program_path, compiler_args=['-static'])
    return program_path
