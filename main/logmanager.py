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

import datetime
import faulthandler
import logging
import os
from io import TextIOWrapper
from typing import Optional

logger = logging.getLogger(__name__)

LOG_DIR: str = "../logs"
DATE_FMT: str = "%Y-%m-%d_%H%M"


class LogManager:
    """Manages log files and ensures that seg-faults are recorded."""

    def __init__(self) -> None:
        self.start_time: datetime.datetime = datetime.datetime.now()
        self.fault_file_path: Optional[str] = None
        self.fault_file: Optional[TextIOWrapper] = None

    def start_logging(self) -> None:
        """Make a log file for the current session and start logging to it."""

        if not os.path.exists("../logs"):
            try:
                os.mkdir(LOG_DIR)
            except OSError:
                logger.exception(
                    "Logging is disabled: couldn't make a log directory.")
                return
        elif os.path.isfile(LOG_DIR):
            logger.error(f"Logging is disabled: '{LOG_DIR}' is a file, \
  not a directory.")
            return

        a_week_ago: str = (
                self.start_time - datetime.timedelta(days=7)
        ).strftime(DATE_FMT)
        try:
            for log_name in os.listdir(LOG_DIR):
                # This may also delete unusually named files.
                if a_week_ago > log_name:
                    os.remove(os.path.join(LOG_DIR, log_name))
        except OSError as e:
            logger.exception(f"Failed to delete old logs: {e}.")

        # Go ahead and append to the previous file if the program is started
        # multiple times in a minute.
        path_fmt = os.path.join(LOG_DIR, DATE_FMT + ".log")
        path = self.start_time.strftime(path_fmt)
        logging.basicConfig(
            filename=path,
            encoding="utf-8",
            format="%(levelname)s %(asctime)s %(name)s: %(message)s",
            level=logging.DEBUG
        )
        logger.info("Logging initialized.")

    def start_fault_handler(self) -> None:
        """Make a log file specifically for reporting seg-fault tracebacks."""

        path_fmt = os.path.join(LOG_DIR, DATE_FMT + "_seg_fault.log")
        self.fault_file_path = self.start_time.strftime(path_fmt)
        try:
            self.fault_file = open(self.fault_file_path, "w")
            faulthandler.enable(self.fault_file)
        except OSError as e:
            logger.exception(f"Couldn't open the seg-fault file; \
fault logging is disabled: {e}.")

    def end(self) -> None:
        """Close log files and remove the seg-fault temporary log file."""

        assert self.fault_file is not None, \
            "Must start the fault handler first."
        assert self.fault_file_path is not None, \
            "Must start the fault handler first."

        try:
            self.fault_file.close()
            # If we made it to the end safely, then no faults were recorded.
            os.remove(self.fault_file_path)
        except OSError as e:
            logger.exception(f"Failed to close the seg-fault file: {e}.")
        logging.shutdown()
