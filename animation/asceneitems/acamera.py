import logging
from typing import (
    Any,
    Optional,
)

from vtkmodules.vtkRenderingCore import vtkCamera

from animation.asceneitems.asceneitem import ASceneItem
from animation.aview import AView
from sceneitems.sceneitem import (
    load_bool,
    load_float,
    load_vec,
)

logger = logging.getLogger(__name__)


class ACamera(ASceneItem):
    """Stores the VTK camera object and manages its UI data."""

    INITIAL_CHECK_STATE: Optional[bool] = None

    def __init__(self, view_frame: AView) -> None:
        super().__init__()

        view_frame.renderer.ResetCamera()
        self.camera: vtkCamera = view_frame.renderer.GetActiveCamera()

        # Orthographic view.
        self.camera.ParallelProjectionOn()
        # Parallel scale is half the height of the viewport in
        # world-coordinate distances.
        self.camera.SetParallelScale(900)
        # Look at the origin.
        self.camera.SetFocalPoint(0, 0, 0)
        # The view is orthographic, so view distance doesn't matter, but it
        # needs to be beyond the volume, or clipping will occur.
        self.camera.SetClippingRange(0.1, 100000)
        self.camera.SetPosition(0, 0, 10000)
        self.camera.SetViewUp(0, -1, 0)  # Y increases with depth.
        self.camera.Azimuth(30)
        self.camera.Elevation(10)

        self.linear_interp: bool = True
        view_frame.v_prop.SetInterpolationType(int(self.linear_interp))

    def update_interp(self, view_frame: AView) -> None:
        """Set the VTK interpolation type based on the internal value "linear_interp".

        Must call this after "from_struct" to pass the view frame.
        """

        view_frame.v_prop.SetInterpolationType(int(self.linear_interp))

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.

        Must call "set_interp" after to finish the initialization.
        """

        errors: list[str] = super().from_struct(struct)
        linear_interp = load_bool("linear_interpolation", struct, errors)
        vtk_camera_from_struct(self.camera, struct, errors)

        if len(errors) > 0:
            return errors

        self.linear_interp = linear_interp
        self.update_view()
        return []


def vtk_camera_from_struct(camera: vtkCamera, struct: dict[str, Any], errors: list[str]) -> None:
    """Update the passed VTK camera object using data from the struct."""

    position = load_vec("position", 3, struct, errors)
    focal_point = load_vec("focal_point", 3, struct, errors)
    # For backwards-compatibility, roll can also be specified.
    use_view_up: bool = True
    if "roll" in struct and "view_up" not in struct:
        roll = load_float("roll", struct, errors)
        use_view_up = False
    else:
        view_up = load_vec("view_up", 3, struct, errors)
    scale = load_float("scale", struct, errors, min_=0.1)
    orthographic = load_bool("orthographic", struct, errors)

    if len(errors) > 0:
        return

    camera.SetPosition(position)
    camera.SetFocalPoint(focal_point)
    if use_view_up:
        # noinspection PyUnboundLocalVariable
        camera.SetViewUp(view_up)
    else:
        # noinspection PyUnboundLocalVariable
        camera.SetRoll(roll)
    camera.SetParallelScale(scale)
    camera.SetParallelProjection(orthographic)


def vtk_camera_to_struct(camera: vtkCamera) -> dict[str, Any]:
    """Create a serializable structure containing the VTK camera data."""

    return {
        "save_keyframes": False,
        "type": "Camera",
        "position": list(camera.GetPosition()),
        "focal_point": list(camera.GetFocalPoint()),
        "view_up": list(camera.GetViewUp()),
        "scale": camera.GetParallelScale(),
        "orthographic": bool(camera.GetParallelProjection()),
        "linear_interpolation": True
    }
