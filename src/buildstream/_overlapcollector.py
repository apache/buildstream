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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Optional, List, Tuple
from .plugin import Plugin
from .types import CoreWarnings, OverlapAction
from .utils import FileListResult

if TYPE_CHECKING:
    from typing import Dict

    # pylint: disable=cyclic-import
    from .element import Element

    # pylint: enable=cyclic-import


# OverlapCollector()
#
# Collects results of Element.stage_artifact() and saves
# them in order to raise a proper overlap error at the end
# of staging.
#
# Args:
#    element (Element): The element for which we are staging artifacts
#
class OverlapCollector:
    def __init__(self, element: "Element"):

        # The Element we are staging for, on which we'll issue warnings
        self._element = element  # type: Element

        # The list of sessions
        self._sessions = []  # type: List[OverlapCollectorSession]

        # The active session, if any
        self._session = None  # type: Optional[OverlapCollectorSession]

    # session()
    #
    # Create a session for collecting overlaps, calls to OverlapCollector.collect_stage_result()
    # are expected to always occur within the context of a session (this context manager).
    #
    # Upon exiting this context, warnings and/or errors will be issued for any overlaps
    # which occurred either as a result of overlapping files within this session, or
    # as a result of files staged during this session, overlapping with files staged in
    # previous sessions in this OverlapCollector.
    #
    # Args:
    #    action (OverlapAction): The action to take for this overall session's overlaps with other sessions
    #    location (str): The Sandbox relative location this session was created for
    #
    @contextmanager
    def session(self, action: str, location: Optional[str]):
        assert self._session is None, "Stage session already started"

        if location is None:
            location = "/"

        self._session = OverlapCollectorSession(self._element, action, location)

        # Run code body where staging results can be collected.
        yield

        # Issue warnings for the current session, passing along previously completed sessions
        self._session.warnings(self._sessions)

        # Store the newly ended session and end the session
        self._sessions.append(self._session)
        self._session = None

    # collect_stage_result()
    #
    # Collect and accumulate results of Element.stage_artifact()
    #
    # Args:
    #    element (Element): The name of the element staged
    #    result (FileListResult): The result of Element.stage_artifact()
    #
    def collect_stage_result(self, element: "Element", result: FileListResult):
        assert self._session is not None, "Staging files outside of staging session"

        self._session.collect_stage_result(element, result)


# OverlapCollectorSession()
#
# Collect the results of a single session
#
# Args:
#    element (Element): The element for which we are staging artifacts
#    action (OverlapAction): The action to take for this overall session's overlaps with other sessions
#    location (str): The Sandbox relative location this session was created for
#
class OverlapCollectorSession:
    def __init__(self, element: "Element", action: str, location: str):

        # The Element we are staging for, on which we'll issue warnings
        self._element = element  # type: Element

        # The OverlapAction for this session
        self._action = action  # type: str

        # The Sandbox relative directory this session was created for
        self._location = location  # type: str

        # Dictionary of files which were ignored (See FileListResult()), keyed by element unique ID
        self._ignored = {}  # type: Dict[int, List[str]]

        # Dictionary of files which were staged, keyed by element unique ID
        self._files_written = {}  # type: Dict[int, List[str]]

        # Dictionary of element IDs which overlapped, keyed by the file they overlap on
        self._overlaps = {}  # type: Dict[str, List[int]]

    # collect_stage_result()
    #
    # Collect and accumulate results of Element.stage_artifact()
    #
    # Args:
    #    element (Element): The name of the element staged
    #    result (FileListResult): The result of Element.stage_artifact()
    #
    def collect_stage_result(self, element: "Element", result: FileListResult):

        for overwritten_file in result.overwritten:

            overlap_list = None
            try:
                overlap_list = self._overlaps[overwritten_file]
            except KeyError:

                # Create a fresh list
                #
                self._overlaps[overwritten_file] = overlap_list = []

                # Search files which were staged in this session, start the
                # list off with the bottom most element
                #
                for element_id, staged_files in self._files_written.items():
                    if overwritten_file in staged_files:
                        overlap_list.append(element_id)
                        break

            # Add the currently staged element to the overlap list, it might be
            # the only element in the list if it overlaps with a file staged
            # from a previous session.
            #
            overlap_list.append(element._unique_id)

        # Record written files and ignored files.
        #
        self._files_written[element._unique_id] = result.files_written
        if result.ignored:
            self._ignored[element._unique_id] = result.ignored

    # warnings()
    #
    # Issue any warnings as a batch as a result of staging artifacts,
    # based on the results collected with collect_stage_result().
    #
    # Args:
    #    sessions (list): List of previously completed sessions
    #
    def warnings(self, sessions: List["OverlapCollectorSession"]):

        # Collect a table of filenames which overlapped something from outside of this session.
        #
        external_overlaps = {}  # type: Dict[str, int]

        #
        # First issue the warnings for this session
        #
        if self._overlaps:
            overlap_warning = False
            detail = "Staged files overwrite existing files in staging area: {}\n".format(self._location)
            for filename, element_ids in self._overlaps.items():

                # If there is only one element in the overlap list, it means it has
                # overlapped a file from a previous session.
                #
                # Ignore it and handle the warning below
                #
                if len(element_ids) == 1:
                    external_overlaps[filename] = element_ids[0]
                    continue

                # Filter whitelisted elements out of the list of overlapping elements
                #
                # Ignore the bottom-most element as it does not overlap anything.
                #
                overlapping_element_ids = element_ids[1:]
                warning_elements = self._filter_whitelisted(filename, overlapping_element_ids)

                if warning_elements:
                    overlap_warning = True

                detail += self._overlap_detail(filename, warning_elements, element_ids)

            if overlap_warning:
                self._element.warn(
                    "Non-whitelisted overlaps detected", detail=detail, warning_token=CoreWarnings.OVERLAPS
                )

        if self._ignored:
            detail = "Not staging files which would replace non-empty directories in staging area: {}\n".format(
                self._location
            )
            for element_id, ignored_filenames in self._ignored.items():
                element = Plugin._lookup(element_id)
                detail += "\nFrom {}:\n".format(element._get_full_name())
                detail += "  " + "  ".join(
                    ["{}\n".format(os.path.join(self._location, filename)) for filename in ignored_filenames]
                )
            self._element.warn(
                "Not staging files which would have replaced non-empty directories",
                detail=detail,
                warning_token=CoreWarnings.UNSTAGED_FILES,
            )

        if external_overlaps and self._action != OverlapAction.IGNORE:
            detail = "Detected file overlaps while staging elements into: {}\n".format(self._location)

            # Find the session responsible for the overlap
            #
            for filename, element_id in external_overlaps.items():
                absolute_filename = os.path.join(self._location, filename)
                overlapped_id, location = self._search_stage_element(absolute_filename, sessions)
                element = Plugin._lookup(element_id)
                overlapped = Plugin._lookup(overlapped_id)
                detail += "{}: {} overlaps files previously staged by {} in: {}\n".format(
                    absolute_filename, element._get_full_name(), overlapped._get_full_name(), location
                )

            if self._action == OverlapAction.WARNING:
                self._element.warn("Overlaps detected", detail=detail, warning_token=CoreWarnings.OVERLAPS)
            else:
                from .element import ElementError

                raise ElementError("Overlaps detected", detail=detail, reason="overlaps")

    # _search_stage_element()
    #
    # Search the sessions list for the element responsible for staging the given file
    #
    # Args:
    #    filename (str): The sandbox relative file which was overwritten
    #    sessions (List[OverlapCollectorSession])
    #
    # Returns:
    #    element_id (int): The unique ID of the element responsible
    #    location (str): The sandbox relative staging location where element_id was staged
    #
    def _search_stage_element(self, filename: str, sessions: List["OverlapCollectorSession"]) -> Tuple[int, str]:
        for session in reversed(sessions):
            for element_id, staged_files in session._files_written.items():
                if any(
                    staged_file
                    for staged_file in staged_files
                    if os.path.join(session._location, staged_file) == filename
                ):
                    return element_id, session._location

        assert False, "Could not find element responsible for staging: {}".format(filename)

        # Silence the linter with an unreachable return statement
        return None, None

    # _filter_whitelisted()
    #
    # Args:
    #    filename (str): The staging session relative filename
    #    element_ids (List[int]): Ordered list of elements
    #
    # Returns:
    #    (List[Element]): The list of element objects which are not whitelisted
    #
    def _filter_whitelisted(self, filename: str, element_ids: List[int]):
        overlap_elements = []

        for element_id in element_ids:
            element = Plugin._lookup(element_id)
            if not element._file_is_whitelisted(filename):
                overlap_elements.append(element)

        return overlap_elements

    # _overlap_detail()
    #
    # Get a string to describe overlaps on a filename
    #
    # Args:
    #    filename (str): The filename being overlapped
    #    overlap_elements (List[Element]): A list of Elements overlapping
    #    element_ids (List[int]): The ordered ID list of elements which staged this file
    #
    def _overlap_detail(self, filename, overlap_elements, element_ids):
        filename = os.path.join(self._location, filename)
        if overlap_elements:
            overlap_element_names = [element._get_full_name() for element in overlap_elements]
            overlap_order_elements = [Plugin._lookup(element_id) for element_id in element_ids]
            overlap_order_names = [element._get_full_name() for element in overlap_order_elements]
            return "{}: {} {} not permitted to overlap other elements, order {} \n".format(
                filename,
                " and ".join(overlap_element_names),
                "is" if len(overlap_element_names) == 1 else "are",
                " above ".join(reversed(overlap_order_names)),
            )
        else:
            return ""
