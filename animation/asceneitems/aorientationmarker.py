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

from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor

from animation.asceneitems.asceneitem import ASceneItem
from sceneitems.sceneitem import (
    load_vec,
)

logger = logging.getLogger(__name__)


class AOrientationMarker(ASceneItem):
    """Stores the vtkOrientationMarkerWidget and manages its UI data."""

    INITIAL_CHECK_STATE: Optional[bool] = False

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

        self.width_frac: float = 0.2
        self.vtk_widget = vtkOrientationMarkerWidget()
        self.vtk_widget.SetOrientationMarker(self.actor)
        # Position as lower right in the viewport.
        self.vtk_widget.SetViewport(1 - self.width_frac, 0, 1, self.width_frac)
        self.vtk_widget.SetZoom(1.5)
        self.vtk_widget.SetInteractor(interactor)

    def update_visibility(self) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        if self.checked:
            self.vtk_widget.EnabledOn()
            self.vtk_widget.InteractiveOn()
        else:
            self.vtk_widget.EnabledOff()

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
