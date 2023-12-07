import logging
from typing import (
    Any,
    Optional,
)

from vtkmodules.vtkCommonDataModel import vtkPlaneCollection

from animation.asceneitems.acamera import ACamera
from animation.asceneitems.aclippingplane import AClippingPlane
from animation.asceneitems.aclippingspline import AClippingSpline
from animation.asceneitems.acontrolpoint import AControlPoint
from animation.asceneitems.aimagechannel import AImageChannel
from animation.asceneitems.aorientationmarker import AOrientationMarker
from animation.asceneitems.ascalebar import AScaleBar
from animation.aview import AView
from scene import (
    MAX_ACTIVE_PLANES,
    MAX_CHANNELS,
)
from sceneitems.sceneitem import (
    load_int,
    Vec3,
)
from timeline import Timeline
from volumeimage import (
    ImageBounds,
    VolumeImage,
)

logger = logging.getLogger(__name__)


class AMainScene:
    """Stores many types of objects related to the 3D view.

    A scene list contains one camera object for manipulating the view, a
    scale bar, a gimbal, a smooth clipper with any number of control
    points, and an unlimited number of clipping planes. It also contains
    the volume settings object, but this is not part of the list. The
    scene is able to write and read itself from a file by calling the
    serialize and deserialize methods on each of its elements.
    """

    def __init__(self, view_frame: AView, timeline: Timeline) -> None:
        self.view_frame: AView = view_frame
        self.bounds: Optional[ImageBounds] = None
        self.last_volume: Optional[VolumeImage] = None

        # Make all the possible channels, but only list one initially.
        self.image_channels: list[AImageChannel] = [
            AImageChannel(i) for i in range(MAX_CHANNELS)
        ]
        self.scale_bar = AScaleBar(view_frame.renderer)
        self.camera = ACamera(view_frame)
        self.orientation_marker = AOrientationMarker(view_frame.interactor)
        self.clipping_spline = AClippingSpline(view_frame, timeline)
        self.planes: list[AClippingPlane] = []

    def volume_update(self, volume: VolumeImage) -> None:
        """Called whenever the active volume is replaced."""

        self.last_volume = volume
        self.bounds = volume.get_bounds()
        scalar_range = volume.get_scalar_range()
        logger.debug(f"Volume, bound={self.bounds}, range={scalar_range}")
        for chan in self.image_channels:
            chan.scalar_range = scalar_range
            chan.update_v_prop(self.view_frame)
        for plane in self.planes:
            plane.place(self.bounds)
        self.clipping_spline.update_bounds(self.bounds)
        self.clipping_spline.attach_mask(volume)

    def update_clipping_planes(self) -> None:
        """Set the active clipping planes in the VTK volume mapper.

        This can be used as a callback when the clipping plane widget is
        moved, in which case it is passed a vtkImplicitPlaneWidget and the
        string, "InteractionEvent", as arguments, which are ignored.
        """

        logger.info("update_clipping_planes")

        vtk_planes = vtkPlaneCollection()
        n = 0
        for plane in self.planes:
            # Limit the number of possible clipping planes active at once to
            # prevent an error from occurring.
            if plane.checked:  # type: ignore
                n += 1
                assert n <= MAX_ACTIVE_PLANES, "Clipping plane limit exceeded."
                vtk_plane = plane.get_vtk_plane()
                vtk_planes.AddItem(vtk_plane)
        self.view_frame.v_mapper.SetClippingPlanes(vtk_planes)

    def from_struct(self, scene_struct: list[dict[str, Any]]) -> list[str]:
        """Reconstructs the scene items based on the data given in scene_struct.

        Updates all the changed widgets when done and returns any errors
        that may have occurred while decoding.
        """

        logger.debug("From struct.")

        if type(scene_struct) != list:
            return [f"Scene should be a list of items, not {type(scene_struct)}"]

        # Unique element such as the Camera shouldn't exist more than once.
        encountered: set[str] = set()
        errors: list[str] = []
        new_planes: list[AClippingPlane] = []
        new_cps: list[AControlPoint] = []
        new_channels: list[bool] = [False] * MAX_CHANNELS
        new_clipping_spline_struct: Optional[Any] = None
        # Now all of those new objects need to be reinitialized from the scene_struct.
        for item_struct in scene_struct:
            if type(item_struct) != dict:
                errors.append(f"Scene items must be objects, not {type(item_struct)}")
                continue
            t = item_struct["type"]
            if t in encountered and t in ["VolumeInfo", "Camera", "ScaleBar",
                                          "OrientationMarker", "ClippingSpline"]:
                errors.append(f"Multiple counts of {t} in scene file")
                continue
            if t == "VolumeInfo":
                pass  # This data exists only for keyframes; don't load it.
            elif t == "Camera":
                err = self.camera.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    self.camera.update_interp(self.view_frame)
                    self.scale_bar.update_visibility()
            elif t == "ScaleBar":
                err = self.scale_bar.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    self.scale_bar.update_visibility()
            elif t == "OrientationMarker":
                err = self.orientation_marker.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    self.orientation_marker.update_visibility()
            elif t == "ClippingSpline":
                # Defer this until after the control points are done so
                # initialization can happen correctly.
                new_clipping_spline_struct = item_struct
            elif t == "ControlPoint":
                item = AControlPoint(Vec3(0., 0., 0.), self.view_frame)
                err = item.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    new_cps.append(item)
            elif t == "ClippingPlane":
                item = AClippingPlane(self.view_frame.interactor)
                err = item.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    new_planes.append(item)
            elif t == "ImageChannel":
                channel_id = load_int("channel_id", item_struct, errors, min_=0, max_=MAX_CHANNELS - 1)
                if channel_id is None:
                    continue
                if new_channels[channel_id]:
                    errors.append(f"Multiple counts of {t} #{channel_id} in scene file")
                item = self.image_channels[channel_id]
                err = item.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    new_channels[channel_id] = True
            else:
                errors.append(f"Unrecognized item type: '{t}'")
                continue
            encountered.add(t)

        # Set up all the image channels. Leave any existing channel items where
        # they are, and put any new channel items after the last item removed.
        if any(new_channels):
            for i, chan in enumerate(self.image_channels):
                chan.exists = new_channels[i]
                chan.update_v_prop(self.view_frame)

        # Set up all the clipping planes.
        if new_planes:
            # Only clear the existing set of planes if at least one
            # plane exists in the scene file.
            for plane in self.planes:
                plane.deselect()
            self.planes = []
            n_active_planes = 0
            for plane in new_planes:
                if n_active_planes < MAX_ACTIVE_PLANES:
                    n_active_planes += int(plane.checked)
                else:
                    errors.append(f"Too many planes simultaneously active ({MAX_ACTIVE_PLANES} allowed)")
                    plane.set_checked(False)
                self.planes.append(plane)
                if self.bounds is not None:
                    plane.place(self.bounds)
            logger.debug("Added planes.")
            self.update_clipping_planes()

        # Set up the clipping spline and all its control points.
        if new_cps:
            # Remove old control points.
            for cp in reversed(self.clipping_spline.mask.control_points):
                self.clipping_spline.mask.delete_cp(cp)
                cp.deselect()

            # Insert new control points after the clipping spline, starting
            # with the last so the order is preserved.
            for cp in reversed(new_cps):
                if self.bounds is not None:
                    cp.place(self.bounds)
                cp.update_visibility()
                self.clipping_spline.mask.add_cp(cp)

        if new_clipping_spline_struct is not None:
            errors.extend(self.clipping_spline.from_struct(new_clipping_spline_struct))
        else:
            self.clipping_spline.attach_mask()

        return errors
