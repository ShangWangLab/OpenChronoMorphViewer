import logging
from typing import (
    Any,
    Optional,
    Sequence,
)

from vtkmodules.vtkFiltersSources import vtkSphereSource
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)

from animation.asceneitems.aplanecontroller import APlaneController
from animation.aview import AView
from sceneitems.sceneitem import Vec3

logger = logging.getLogger(__name__)


class AControlPoint(APlaneController):
    """Stores the VTK plane widget and manages its UI data.

    This is like a clipping plane, but it doesn't actually clip; it is
    instead intended for use with a smooth clipper.
    """

    INITIAL_CHECK_STATE: Optional[bool] = True

    def __init__(self, origin: Vec3, view_frame: AView) -> None:
        self.view_frame = view_frame
        self.sphere_source = vtkSphereSource()
        self.sphere_source.SetRadius(15)  # Units of microns.
        self.sphere_mapper = vtkPolyDataMapper()
        self.sphere_mapper.SetInputConnection(self.sphere_source.GetOutputPort())
        self.sphere_actor = vtkActor()
        self.sphere_actor.SetMapper(self.sphere_mapper)
        self.sphere_actor.GetProperty().SetColor(0, 1, 0)  # Green.
        self.sphere_actor.PickableOn()
        view_frame.renderer.AddActor(self.sphere_actor)

        normal = Vec3(0, 1, 0)
        super().__init__(view_frame.interactor, origin, normal)

    def update_visibility(self) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        self.sphere_actor.SetVisibility(self.checked)

    def deselect(self) -> None:
        """Hide the VTK widget for controlling the plane."""

        super().deselect()
        self.view_frame.renderer.RemoveActor(self.sphere_actor)

    def set_origin(self, origin: Vec3) -> None:
        """Set the origin of the VTK implicit plane."""

        super().set_origin(origin)
        self.sphere_source.SetCenter(origin)


def cp_origin_to_struct(origin: Sequence[float], show_origin: bool = False) -> dict[str, Any]:
    """Create a dummy struct for a control point with default settings except
    for the origin, which is specified.

    :param origin: An iterable containing 3 numbers. Will be type converted, as needed.
    :param show_origin: When true, a ball will indicate the position of the control point.
    :return: A struct representing this control point as a scene object.
    """

    return {
        "save_keyframes": False,
        "checked": show_origin,
        "type": "ControlPoint",
        "name": "Dummy",
        "origin": list(map(float, origin)),
        "normal": [1, 0, 0]
    }
