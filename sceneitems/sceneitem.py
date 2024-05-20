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
import math
from typing import (
    Any,
    NamedTuple,
    Optional,
)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import (
    QListWidgetItem,
    QListWidget,
    QWidget,
)

from main.viewframe import ViewFrame

logger = logging.getLogger(__name__)


class Vec3(NamedTuple):
    x: float
    y: float
    z: float


class SceneItem:
    """The generic super-class for elements occupying space in the list
    widget as part of the Scene.
    """

    ICON_PATH: str = ""
    # The name shown on the item next to the icon.
    INITIAL_LABEL: str = "Scene Item"
    # Set the check state as None to disable checking.
    INITIAL_CHECK_STATE: Optional[Qt.CheckState] = None
    UI_SETTINGS_CLASS: Any = None

    def __init__(self) -> None:
        self.ui_settings: Any = None
        self.list_widget: Optional[QListWidgetItem] = None
        self.scene_list: Optional[QListWidget] = None
        # Is the checkbox checked?
        self.checked: bool = self.INITIAL_CHECK_STATE == Qt.Checked
        # Is this the selected scene item?
        self.active: bool = False
        self.save_keyframes: bool = False

    def add_to_scene_list(self, scene_list: Optional[QListWidget]) -> None:
        """Make a list widget item and adds it to the scene list."""

        self.list_widget = QListWidgetItem(
            QIcon(self.ICON_PATH),
            self.INITIAL_LABEL,
            scene_list
        )
        # Add a handle, so we can iterate through the scene item list and
        # retrieve the object for manipulation.
        self.list_widget.scene_item = self  # type: ignore

        if self.INITIAL_CHECK_STATE is not None:
            self.list_widget.setCheckState(Qt.Checked if self.checked else Qt.Unchecked)  # type: ignore

    def remove_from_scene_list(self, scene_list: QListWidget) -> None:
        """Remove the list item widget from the scene list."""

        self.deselect()
        if self.list_widget is None:
            return
        scene_list.takeItem(scene_list.row(self.list_widget))

    def update_visibility(self, view_frame: ViewFrame) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        self.checked = self.list_widget.checkState() == Qt.Checked  # type: ignore

    def make_settings_widget(self) -> QWidget:
        """Create a widget to fill the scene settings field.

        Called when this object is selected and becomes active.
        """

        settings_widget: QWidget = QWidget()
        self.ui_settings = self.UI_SETTINGS_CLASS()
        self.ui_settings.setupUi(settings_widget)
        self.active = True
        self.update_view()

        return settings_widget

    def deselect(self) -> None:
        """Signal that this object is no longer active in the settings panel."""

        if self.active:
            self.active = False
            self.ui_settings = None

    def set_checked(self, checked: bool) -> None:
        """Check or uncheck the associated list item.

        If this item hasn't been added to the list, it is ignored.
        """

        logger.debug(f"set_checked({checked})")
        if self.INITIAL_CHECK_STATE is None:
            logger.debug(f"This type of item can't be checked.")
            return
        if self.list_widget is None:
            logger.debug(f"There is no item to check.")
            return
        self.list_widget.setCheckState(Qt.Checked if checked else Qt.Unchecked)  # type: ignore
        # Must be set after updating the list widget so the "item changed" event
        # can be handled properly.
        self.checked = checked

    def update_view(self, *_: Any) -> None:
        """Fill out visible information in the UI and VTK view port.

        This method might be called when the scroll area is not visible, in
        which case the UI will not be updated.

        This method can also be used as a VTK event callback, in which case
        the arguments are ignored.
        """

        if self.checked or self.INITIAL_CHECK_STATE is None:
            self._update_vtk()
        if self.active:
            self._update_ui()

    def _update_vtk(self) -> None:
        """Update information related to the VTK viewport."""

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        state = Qt.Checked if self.save_keyframes else Qt.Unchecked  # type: ignore
        self.ui_settings.checkbox_save_keyframes.setCheckState(state)

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        def toggle_keyframes(state: Qt.CheckState) -> None:
            self.save_keyframes = state == Qt.Checked  # type: ignore

        self.ui_settings.checkbox_save_keyframes.stateChanged.connect(
            toggle_keyframes
        )

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct: dict[str, Any] = dict()
        struct["type"] = "SceneItem"  # Usually overwritten by the child.
        if self.INITIAL_CHECK_STATE is not None:
            struct["checked"] = self.checked
        struct["save_keyframes"] = self.save_keyframes
        return struct

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = []
        if self.INITIAL_CHECK_STATE is not None:
            checked = load_bool("checked", struct, errors)
            if checked is not None:
                self.set_checked(checked)
        save_keyframes = load_bool("save_keyframes", struct, errors)
        if save_keyframes is not None:
            self.save_keyframes = save_keyframes
        return errors


def load_str(name: str, struct: dict[str, Any], errors: list[str]) -> Optional[str]:
    """Helper function for reading a named string from a struct and reporting errors.

    Error messages are appended to the passed "errors" list.
    """

    if name not in struct:
        errors.append(f"'{name}' is missing")
        return None
    value = struct[name]
    if type(value) != str:
        errors.append(f"'{name}' must be a string")
        return None
    return value


def load_bool(name: str, struct: dict[str, Any], errors: list[str]) -> Optional[bool]:
    """Helper function for reading a named bool from a struct and reporting errors.

    Error messages are appended to the passed "errors" list.
    """

    if name not in struct:
        errors.append(f"'{name}' is missing")
        return None
    value = struct[name]
    if type(value) != bool:
        errors.append(f"'{name}' must be a boolean")
        return None
    return value


def load_int(name: str,
             struct: dict[str, Any],
             errors: list[str],
             min_: Optional[int] = None,
             max_: Optional[int] = None) -> Optional[int]:
    """Helper function for reading a named int from a struct and reporting errors.

    "min_" and "max_" represent the minimum and maximum acceptable values.

    Error messages are appended to the passed "errors" list.
    """

    if name not in struct:
        errors.append(f"'{name}' is missing")
        return None
    value = struct[name]
    if type(value) != int:
        errors.append(f"'{name}' must be an integer")
        return None
    if min_ is not None and value < min_ or max_ is not None and max_ < value:
        errors.append(f"'{name}' is out of range [{min_} to {max_}]")
        return None
    return value


def load_float(name: str,
               struct: dict[str, Any],
               errors: list[str],
               min_: Optional[float] = None,
               max_: Optional[float] = None) -> Optional[float]:
    """Helper function for reading a named float from a struct and reporting errors.

    "min_" and "max_" represent the minimum and maximum acceptable values.

    Error messages are appended to the passed "errors" list.
    """

    if name not in struct:
        errors.append(f"'{name}' is missing")
        return None
    value = struct[name]
    if type(value) not in (float, int) or math.isinf(value) or math.isnan(value):
        errors.append(f"'{name}' must be a decimal number")
        return None
    if min_ is not None and value < min_ or max_ is not None and max_ < value:
        errors.append(f"'{name}' is out of range [{min_} to {max_}]")
        return None
    return float(value)


def load_vec(name: str,
             n_dims: int,
             struct: dict[str, Any],
             errors: list[str],
             min_: Optional[float] = None,
             max_: Optional[float] = None) -> Optional[list[float]]:
    """Helper function for reading a named N-D float vector from a struct and reporting errors.

    "min_" and "max_" represent the minimum and maximum acceptable values for
    each component of the vector.

    Error messages are appended to the passed "errors" list.
    """

    if name not in struct:
        errors.append(f"'{name}' is missing")
        return None
    value = struct[name]
    if type(value) != list or len(value) != n_dims:
        errors.append(f"'{name}' must be a {n_dims}D vector")
        return None
    if any(type(x) not in (float, int) or math.isinf(x) or math.isnan(x) for x in value):
        errors.append(f"'{name}' must contain decimal numbers")
        return None
    if (min_ is not None and any(x < min_ for x in value)
            or max_ is not None and any(max_ < x for x in value)):
        errors.append(f"'{name}' contains values out of range [{min_} to {max_}]")
        return None
    return list(map(float, value))


def load_color(name: str, struct: dict[str, Any], errors: list[str]) -> Optional[QColor]:
    """Helper function for reading a named color from a struct and reporting errors.

    Error messages are appended to the passed "errors" list.
    """

    if name not in struct:
        errors.append(f"'{name}' is missing")
        return None
    value = struct[name]
    if type(value) != str:
        errors.append(f"'{name}' must be a color string, such as #ff80a1")
        return None
    color = QColor(value)
    if not color.isValid():
        errors.append(f"'{name}' must be a color string, such as #ff80a1")
        return None
    return color
