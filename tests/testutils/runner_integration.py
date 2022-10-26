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
#  Authors:
#         Will Salmon <will.salmon@codethink.co.uk>

import time


def wait_for_cache_granularity():
    # This isn't called very often so has minimal impact on test runtime.
    # If this changes it may be worth while adding a more sophisticated approach.
    """
    Mitigate the coarse granularity of the gitlab runners mtime

    This function waits for the mtime to increment so that the cache can sort by mtime and
    get the most recent results.
    """
    time.sleep(1.1)
