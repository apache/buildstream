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
from typing import Optional

from .node import MappingNode, _SYNTHETIC_FILE_INDEX, SequenceNode

def load(filename: str, shortname: str, copy_tree: bool = False, project: Optional[object] = None) -> MappingNode: ...
def load_data(
    data: str, file_index: int = _SYNTHETIC_FILE_INDEX, file_name: str | None = None, copy_tree: bool = False
) -> MappingNode: ...
def roundtrip_dump(contents, file=None): ...
def roundtrip_dump_string(node: dict | list) -> str: ...
def roundtrip_load(filename: str, allow_missing: bool = False) -> MappingNode: ...
