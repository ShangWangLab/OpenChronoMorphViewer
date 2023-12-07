import logging
import random
from typing import (
    Any,
    Optional,
)

from vtkmodules.vtkRenderingCore import vtkActor

from animation.asceneitems.acontrolpoint import AControlPoint
from animation.asceneitems.asceneitem import ASceneItem
from animation.aview import AView
from sceneitems.sceneitem import (
    Vec3, load_int, load_bool, load_float,
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
        self.initialized: bool = False
        self.mask: VolumeMaskTPS = VolumeMaskTPS()
        self.bounds: Optional[ImageBounds] = None
        self.show_mesh: bool = False
        self.mesh_actor: Optional[vtkActor] = None

    def update_bounds(self, bounds: ImageBounds) -> None:
        """Update all the bounds on the control point VTK plane widgets."""

        self.bounds = bounds
        for point in self.mask.control_points:
            point.place(bounds)

    def add_ctrl_pt(self) -> None:
        """Create a new control point and add it to the scene view."""

        name = f"Control Point {self.mask.count_cp() + 1}"
        if self.bounds is not None:
            # We want to place the origin at a random spot within the central
            # 70% of the volume.
            r0 = (self.bounds[1] - self.bounds[0]) / 2
            c0 = (self.bounds[1] + self.bounds[0]) / 2
            r1 = (self.bounds[3] - self.bounds[2]) / 2
            c1 = (self.bounds[3] + self.bounds[2]) / 2
            r2 = (self.bounds[5] - self.bounds[4]) / 2
            c2 = (self.bounds[5] + self.bounds[4]) / 2
            origin = Vec3(
                c0 + 0.7 * r0 * (2 * random.random() - 1),
                c1 + 0.7 * r1 * (2 * random.random() - 1),
                c2 + 0.7 * r2 * (2 * random.random() - 1),
            )
        else:
            # We don't know where to place the point, but points cannot occupy
            # the exact same point without causing inconvenience, so we randomly
            # pick +/- 100 microns of the center.
            origin = Vec3(
                100 * (2 * random.random() - 1),
                100 * (2 * random.random() - 1),
                100 * (2 * random.random() - 1),
            )
        point = AControlPoint(origin, self.view_frame)
        if self.bounds is not None:
            point.place(self.bounds)
        self.mask.add_cp(point)
        self.attach_mask()

    def delete_ctrl_pt(self, point: AControlPoint) -> None:
        """Remove the passed control point from the list and the scene view."""

        if self.mask.count_cp() <= 3 and self.initialized:
            # An active spline can't have fewer than 3 control points.
            self._uninitialize_mask()

        self.mask.delete_cp(point)
        self.attach_mask()

    def attach_mask(self, volume: Optional[VolumeImage] = None) -> None:
        """Build and attach the mask to the viewer."""

        if volume is not None:
            self.mask.set_volume(volume)

        if self.mesh_actor is not None:
            self.view_frame.renderer.RemoveActor(self.mesh_actor)
            self.mesh_actor = None

        if self.checked and self.initialized:
            assert self.mask.has_volume, "Initialized without a volume somehow."
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

    def initialize_mask(self) -> None:
        """Initialize the VolumeMaskTPS object.

        Runs on the UI thread; no expensive operations are allowable.

        When "add_points" is True, new points will be added until at least three
        points exist to form a plane.
        """

        # Can only decide how to allocate resources if volumes exist.
        if not self.mask.has_volume:
            return

        logger.info("Initializing.")

        # Make sure there are at least 3 control points.
        for i in range(max(0, 3 - self.mask.count_cp())):
            self.add_ctrl_pt()

        self.mask.initialize(self.timeline)
        self.initialized = True
        self.attach_mask()

    def _uninitialize_mask(self) -> None:
        """Uninitialize the VolumeMaskTPS object."""

        logger.info("Uninitializing.")
        self.mask.uninitialize()
        self.initialized = False
        self.attach_mask()

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
        initialized = load_bool("initialized", struct, errors)

        if len(errors) > 0:
            return errors

        self.mask.set_axis(axis)
        self.mask.set_direction(keep_greater_than)
        self.mask.set_regularization(regularization)
        self.show_mesh = show_mesh

        if self.initialized and not initialized:
            self._uninitialize_mask()
            print("Uninitialized")
        elif not self.initialized and initialized and self.mask.has_volume:
            # I think it's appropriate here to silently ignore the error when initialization is impossible.
            self.initialize_mask()
            print("Initialized")
        else:
            self.attach_mask()
            print("Simply attached mask.")

        return []
