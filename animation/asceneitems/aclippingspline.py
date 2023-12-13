import logging
from typing import (
    Any,
    Optional,
)

from vtkmodules.vtkRenderingCore import vtkActor

from animation.asceneitems.asceneitem import ASceneItem
from animation.aview import AView
from sceneitems.sceneitem import (
    load_bool,
    load_float,
    load_int,
)
from timeline import Timeline
from volumeimage import (
    ImageBounds,
    VolumeImage,
)
from volumemasktps import VolumeMaskTPS

logger = logging.getLogger(__name__)


class AClippingSpline(ASceneItem):
    """Manages the data for the smooth clipper and its UI data.

    This uses a set of control points to create a thin-plate spline as a
    smooth, non-planar clipping surface. The surface is used to generate a
    volume mask to hide voxels on the other side of the mask.
    """

    INITIAL_CHECK_STATE: Optional[bool] = False

    def __init__(self,
                 view_frame: AView,
                 timeline: Timeline) -> None:
        super().__init__()
        self.view_frame = view_frame
        self.timeline = timeline
        self.mask: VolumeMaskTPS = VolumeMaskTPS()
        self.bounds: Optional[ImageBounds] = None
        self.show_mesh: bool = False
        self.mesh_actor: Optional[vtkActor] = None

    def update_bounds(self, bounds: ImageBounds) -> None:
        """Update all the bounds on the control point VTK plane widgets."""

        self.bounds = bounds
        for point in self.mask.control_points:
            point.place(bounds)

    def attach_mask(self, volume: Optional[VolumeImage] = None) -> None:
        """Build and attach the mask to the viewer."""

        if volume is not None:
            self.mask.set_volume(volume)

        if self.mesh_actor is not None:
            self.view_frame.renderer.RemoveActor(self.mesh_actor)
            self.mesh_actor = None

        if self.checked:
            assert self.mask.has_volume(), "A volume was never attached."
            assert self.mask.count_cp() >= 3, "Need 3 control points to make a mask."
            # The volume exists when the VolumeUpdater triggers this method.
            # In that case, it will handle rendering for us.

            if self.show_mesh:
                self.mesh_actor = self.mask.make_mesh()
                self.view_frame.renderer.AddActor(self.mesh_actor)

            mask_vtk = self.mask.get_vtk()
            self.view_frame.v_mapper.SetMaskInput(mask_vtk)
            print("Set mask")
        else:
            self.view_frame.v_mapper.SetMaskInput(None)
            print("Cleared mask")

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        axis = load_int("axis", struct, errors, min_=0, max_=2)
        keep_greater_than = load_bool("keep_greater_than", struct, errors)
        regularization = load_float("smoothing", struct, errors, min_=0)
        show_mesh = load_bool("show_mesh", struct, errors)

        if len(errors) > 0:
            return errors

        self.mask.set_axis(axis)
        self.mask.set_direction(keep_greater_than)
        self.mask.set_regularization(regularization)
        self.show_mesh = show_mesh

        self.attach_mask()

        return []
