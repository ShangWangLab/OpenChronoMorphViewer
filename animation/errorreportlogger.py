#  Open Chrono-Morph Viewer, a project for visualizing volumetric time-series.
#  Copyright © 2024 Andre C. Faubert
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import logging

from errorreporter import FileError

logger = logging.getLogger(__name__)


class ErrorReportLogger:
    """Mimics the ErrorReporter interface, but instead of showing errors to the
    user, errors are simply logged.
    """

    @staticmethod
    def illegal_action(message: str) -> None:
        """Use when the user does something that isn't allowed.

        Opens a pop-up box explaining why the operation isn't permitted.
        """

        logger.warning(f"Illegal action: {message}")

    @staticmethod
    def file_errors(file_errors: list[FileError]) -> None:
        """Show the user a condensed summary of the errors passed.

        Each error message is given its own line. Repeated messages are condensed to
        show "... and x others", up to a maximum of 10 lines.
        """

        for message, file_path in file_errors:
            logger.warning(f"{message} at '{file_path}'.")