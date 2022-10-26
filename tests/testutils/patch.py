#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import subprocess


def apply(file, patch):
    try:
        subprocess.check_output(["patch", file, patch])
    except subprocess.CalledProcessError as e:
        message = "Patch failed with exit code {}\n Output:\n {}".format(e.returncode, e.output)
        print(message)
        raise


def remove(file, patch):
    try:
        subprocess.check_output(["patch", "--reverse", file, patch])
    except subprocess.CalledProcessError as e:
        message = "patch --reverse failed with exit code {}\n Output:\n {}".format(e.returncode, e.output)
        print(message)
        raise
