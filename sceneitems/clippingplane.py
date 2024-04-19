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
    TYPE_CHECKING,
)

from PyQt5.QtCore import Qt
from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor

from sceneitems.planecontroller import PlaneController
from sceneitems.sceneitem import Vec3
from viewframe import ViewFrame

if TYPE_CHECKING:
    from scene import Scene

logger = logging.getLogger(__name__)


class ClippingPlane(PlaneController):
    """Stores the VTK plane widget and manages its UI data."""

    ICON_PATH: str = "ui/graphics/icon_clipping_plane.png"
    INITIAL_CHECK_STATE: Qt.CheckState = Qt.Unchecked  # type: ignore

    def __init__(self,
                 name: str,
                 interactor: vtkGenericRenderWindowInteractor,
                 scene: "Scene") -> None:
        origin = Vec3(0, 0, 0)
        normal = Vec3(1, 1, 0)
        super().__init__(name, interactor, scene.camera, origin, normal)
        self.scene = scene

        self.i_plane.AddObserver(
            vtkCommand.InteractionEvent,
            scene.update_clipping_planes
        )
        self.i_plane.AddObserver(
            vtkCommand.EndInteractionEvent,
            self.update_view
        )

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        super().bind_event_listeners(view_frame)

        def on_delete(_: Any = None) -> None:
            self.scene.delete_plane(self)

        self.ui_settings.button_delete_plane.clicked.connect(on_delete)
        self.ui_settings.button_new_plane.clicked.connect(self.scene.new_plane)

    def normal_to_view(self, _: Any = None) -> None:
        """Turn the plane to point toward the camera."""

        super().normal_to_view()
        self.scene.update_clipping_planes()

    def _input_origin(self) -> None:
        """Called when the normal is set in the UI line edits."""

        super()._input_origin()
        self.scene.update_clipping_planes()

    def _input_normal(self) -> None:
        """Called when the normal is set in the UI line edits."""

        super()._input_normal()
        self.scene.update_clipping_planes()

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "ClippingPlane"
        return struct
