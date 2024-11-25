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

import os
from contextlib import contextmanager

from buildstream._cas import CASCache, CASDProcessManager, CASLogLevel


@contextmanager
def casd_cache(path, messenger=None):
    casd = CASDProcessManager(
        str(path),
        os.path.join(str(path), "..", "logs", "_casd"),
        CASLogLevel.WARNING,
        16 * 1024 * 1024,
        None,
        True,
        None,
    )
    try:
        cascache = CASCache(str(path), casd=casd)
        try:
            yield cascache
        finally:
            cascache.release_resources()
    finally:
        casd.release_resources(messenger)
