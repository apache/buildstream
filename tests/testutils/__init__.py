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
#  Authors: Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#           Tristan Maat <tristan.maat@codethink.co.uk>
#           Sam Thursfield <sam.thursfield@codethink.co.uk>
#           James Ennis <james.ennis@codethink.co.uk>
#           Valentin David <valentin.david@codethink.co.uk>
#           William Salmon <will.salmon@codethink.co.uk>
#

from .artifactshare import create_artifact_share, create_split_share, assert_shared, assert_not_shared, ArtifactShare
from .context import dummy_context
from .element_generators import create_element_size
from .junction import generate_junction
from .runner_integration import wait_for_cache_granularity
from .python_repo import setup_pypi_repo
from .platform import override_platform_uname
