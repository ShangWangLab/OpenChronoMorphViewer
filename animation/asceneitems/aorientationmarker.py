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
