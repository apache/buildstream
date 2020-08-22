#
#  Copyright (C) 2020 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#

import os
from abc import ABC, abstractmethod
from typing import Type

from ..repo import Repo


class BaseSourceTests(ABC):
    @property
    @classmethod
    @abstractmethod
    def KIND(cls) -> str:
        """Human readable name of the source currently being tested."""

    @property
    @classmethod
    @abstractmethod
    def REPO(cls) -> Type[Repo]:
        """Get the repo implementation for the currently tested source."""
