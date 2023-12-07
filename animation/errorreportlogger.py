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