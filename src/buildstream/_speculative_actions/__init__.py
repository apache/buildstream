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

"""
Speculative Actions - Cache Priming Infrastructure
===================================================

This module implements the Speculative Actions feature for BuildStream,
which enables predictive cache priming by recording and replaying compiler
invocations with updated dependency versions.

Key Components:
- generator: Generates SpeculativeActions and artifact overlays after builds
- instantiator: Applies overlays to instantiate actions before builds
"""

from .generator import SpeculativeActionsGenerator
from .instantiator import SpeculativeActionInstantiator

__all__ = ["SpeculativeActionsGenerator", "SpeculativeActionInstantiator"]
