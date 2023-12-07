"""This module contains helpful functions for reporting errors to the user."""

import logging
from typing import NamedTuple

from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject
from PyQt5.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)


class FileError(NamedTuple):
    message: str
    file_path: str


N_SUMMARY_LINES: int = 5


class ErrorReporter(QObject):
    """Show pop-up error message to the user.

    The "dialog_parent" widget passed will be the parent of any dialog boxes created.
    """

    _illegal_action_signal = pyqtSignal(str)
    _file_errors_signal = pyqtSignal(list)

    def __init__(self, dialog_parent: QWidget) -> None:
        super().__init__()

        self.dialog_parent: QWidget = dialog_parent
        self._illegal_action_signal.connect(self._illegal_action_slot)  # type: ignore
        self._file_errors_signal.connect(self._file_errors_slot)  # type: ignore

    def illegal_action(self, message: str) -> None:
        """Use when the user does something that isn't allowed.

        Opens a pop-up box explaining why the operation isn't permitted.
        """

        # noinspection PyUnresolvedReferences
        self._illegal_action_signal.emit(message)

    @pyqtSlot(str)
    def _illegal_action_slot(self, message: str) -> None:
        """Use when the user does something that isn't allowed.

        Opens a pop-up box explaining why the operation isn't permitted.

        Must run on the UI thread.
        """

        logger.warning(f"Illegal action: {message}")
        QMessageBox.warning(self.dialog_parent, "Illegal action", message)

    def file_errors(self, file_errors: list[FileError]) -> None:
        """Show the user a condensed summary of the errors passed.

        Each error message is given its own line. Repeated messages are condensed to
        show "... and x others", up to a maximum of 10 lines.
        """

        # noinspection PyUnresolvedReferences
        self._file_errors_signal.emit(file_errors)

    @pyqtSlot(list)
    def _file_errors_slot(self, file_errors: list[FileError]) -> None:
        """Show the user a condensed summary of the errors passed.

        Each error message is given its own line. Repeated messages are condensed to
        show "... and x others", up to a maximum of 10 lines.

        Must run on the UI thread.
        """

        error_dict: dict[str, list[str]] = dict()
        for message, file_path in file_errors:
            logger.warning(f"{message} at '{file_path}'.")
            if message in error_dict:
                error_dict[message].append(file_path)
            else:
                error_dict[message] = [file_path]

        report_lines: list[str] = []
        for message, file_paths in error_dict.items():
            if len(report_lines) >= N_SUMMARY_LINES:
                report_lines.append(f"... and {len(error_dict) - N_SUMMARY_LINES} other error(s).")
                break
            if len(file_paths) == 1:
                report_lines.append(f"{message} in '{file_paths[0]}'")
            else:
                report_lines.append(
                    f"{message} in '{file_paths[0]}' and {len(file_paths) - 1} other file(s).")

        message: str = "\n\n".join(report_lines)
        QMessageBox.warning(self.dialog_parent, "File error(s)", message)
