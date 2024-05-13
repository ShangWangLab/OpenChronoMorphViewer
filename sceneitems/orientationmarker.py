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
from typing import (
    Any,
    Optional,
)

from PyQt5.QtCore import Qt
from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor

from main.eventfilter import EditDoneEventFilter
from main.validatenumericinput import validate_float
from main.viewframe import ViewFrame
from sceneitems.sceneitem import (
    SceneItem,
    load_vec,
)
from ui.settings_orientation_marker import Ui_SettingsOrientationMarker

logger = logging.getLogger(__name__)


class OrientationMarker(SceneItem):
    """Stores the vtkOrientationMarkerWidget and manages its UI data."""

    ICON_PATH: str = "ui/graphics/icon_orientation_marker.png"
    INITIAL_LABEL: str = "Orientation Marker"
    INITIAL_CHECK_STATE: Qt.CheckState = Qt.Unchecked  # type: ignore
    UI_SETTINGS_CLASS = Ui_SettingsOrientationMarker

    def __init__(self, interactor: vtkGenericRenderWindowInteractor) -> None:
        super().__init__()

        self.actor = vtkAxesActor()
        self.actor.SetShaftTypeToCylinder()
        self.actor.SetXAxisLabelText("X")
        self.actor.SetYAxisLabelText("Y")
        self.actor.SetZAxisLabelText("Z")
        self.actor.SetTotalLength(1., 1., 1.)
        self.actor.SetCylinderRadius(0.5 * self.actor.GetCylinderRadius())
        self.actor.SetConeRadius(1.025 * self.actor.GetConeRadius())
        self.actor.SetSphereRadius(1.5 * self.actor.GetSphereRadius())

        self.edit_width: Optional[EditDoneEventFilter] = None

        self.width_frac: float = 0.2
        self.vtk_widget = vtkOrientationMarkerWidget()
        self.vtk_widget.SetOrientationMarker(self.actor)
        # Position as lower right in the viewport.
        self.vtk_widget.SetViewport(1 - self.width_frac, 0, 1, self.width_frac)
        self.vtk_widget.SetZoom(1.5)
        self.vtk_widget.SetInteractor(interactor)

        def on_interact(*_: Any) -> None:
            x_min, y_min, x_max, y_max = self.vtk_widget.GetViewport()
            self.width_frac = x_max - x_min
            self.update_view()

        self.vtk_widget.AddObserver(vtkCommand.EndInteractionEvent, on_interact)

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        super()._update_ui()
        self.ui_settings.edit_width.setText(f"{100 * self.width_frac:0.1f}")

    def update_visibility(self, view_frame: ViewFrame) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        super().update_visibility(view_frame)
        if self.checked:
            self.vtk_widget.EnabledOn()
            self.vtk_widget.InteractiveOn()
        else:
            self.vtk_widget.EnabledOff()

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        super().bind_event_listeners(view_frame)

        def update_width() -> None:
            """Read and set the width/size of the """

            # Width is given as a percentage.
            new_width = 0.01 * validate_float(
                self.ui_settings.edit_width.text(),
                5, 100
            )
            x_min, y_min, x_max, y_max = self.vtk_widget.GetViewport()
            scale = new_width / self.width_frac
            new_height = scale * (y_max - y_min)

            x_max = x_min + new_width
            y_max = y_min + new_height
            if x_max > 1:
                x_min -= x_max - 1
                x_max = 1
            if y_max > 1:
                y_min -= y_max - 1
                y_max = 1

            self.vtk_widget.SetViewport(x_min, y_min, x_max, y_max)
            self.width_frac = new_width
            self.update_view()
            logger.debug("update_width:VTK_render()")
            view_frame.vtk_render()

        self.edit_width = EditDoneEventFilter(update_width)
        self.ui_settings.edit_width.installEventFilter(self.edit_width)

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "OrientationMarker"
        # Sometimes the viewport moves slightly outside the view frame, so we clamp it.
        struct["viewport"] = [max(0, min(x, 1)) for x in self.vtk_widget.GetViewport()]
        return struct

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        viewport = load_vec("viewport", 4, struct, errors, min_=0, max_=1)

        if len(errors) > 0:
            return errors

        self.vtk_widget.SetViewport(viewport)
        self.update_view()
        return []
