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

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QMainWindow,
    QSizePolicy,
)

from main.validatenumericinput import validate_int
from ui.dialog_render_settings import Ui_dialog_render_settings

logger = logging.getLogger(__name__)


class DialogRenderSettings(QDialog):
    """A dialog box allowing the user to set the size of the render frame."""

    def __init__(self, parent: QMainWindow, view_frame: QFrame) -> None:
        super().__init__(parent)

        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.ui = Ui_dialog_render_settings()
        self.ui.setupUi(self)
        self.accepted.connect(self.on_accept)  # type: ignore
        reset_button = self.ui.dialogButtonBox.button(QDialogButtonBox.Reset)
        reset_button.clicked.connect(self.on_reset)  # type: ignore

        self.view_frame = view_frame
        self.initial_width: int = view_frame.width()
        self.initial_height: int = view_frame.height()
        self.ui.edit_width.setText(str(self.initial_width))
        self.ui.edit_height.setText(str(self.initial_height))

        logger.debug(f"View frame size: {view_frame.width()} x {view_frame.height()}")
        logger.debug(f"Window size: {parent.width()} x {parent.height()}")

    @pyqtSlot()
    def on_accept(self) -> None:
        """When the OK button is pressed.

        Set the rendering frame to a fixed size.
        """

        logger.debug("Accepted render settings")
        width = validate_int(self.ui.edit_width.text(), 1,
                             default=self.initial_width)
        height = validate_int(self.ui.edit_height.text(), 1,
                              default=self.initial_height)
        logger.debug(f"User entered: {width} x {height}")
        self.view_frame.setFixedSize(width, height)
        logger.debug(f"Resulting view frame size: \
{self.view_frame.width()} x {self.view_frame.height()}")

    @pyqtSlot()
    def on_reset(self) -> None:
        """When the Reset button is pressed.

        Clear the size constraints on the render frame.
        """

        logger.debug("Reset render settings")
        self.view_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.view_frame.setMinimumSize(0, 0)
        self.view_frame.setMaximumSize(0xffffff, 0xffffff)
        logger.debug(f"Resulting view frame size: \
{self.view_frame.width()} x {self.view_frame.height()}")
        self.reject()
