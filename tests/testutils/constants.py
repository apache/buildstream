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

# Constants used during BuildStream tests.


# Timeout for short interactive operations (in seconds).
#
# Use this for operations that are expected to finish within a short amount of
# time. Like `bst init`, `bst show` on a small project.
PEXPECT_TIMEOUT_SHORT = 30


# Timeout for longer interactive operations (in seconds).
#
# Use this for operations that are expected to take longer amounts of time,
# like `bst build` on a small project.
PEXPECT_TIMEOUT_LONG = 300
