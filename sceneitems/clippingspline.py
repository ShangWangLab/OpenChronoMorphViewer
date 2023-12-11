import logging
import random
from threading import Thread
from typing import (
    Any,
    Optional,
)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QListWidget,
)

from errorreporter import ErrorReporter
from eventfilter import EditDoneEventFilter
from maskupdater import MaskUpdater
from sceneitems.camera import Camera
from sceneitems.controlpoint import ControlPoint
from sceneitems.sceneitem import (
    SceneItem,
    Vec3, load_int, load_bool, load_float,
)
from timeline import Timeline
from ui.settings_clipping_spline import Ui_SettingsClippingSpline
from validatenumericinput import (
    nice_exp_format,
    validate_float,
)
from viewframe import ViewFrame
from volumeimage import (
    ImageBounds,
    VolumeImage,
)
from volumemasktps import VolumeMaskTPS

logger = logging.getLogger(__name__)


class ClippingSpline(SceneItem):
    """Manages the data for the smooth clipper and its UI data.

    This uses a set of control points to create a thin-plate spline as a
    smooth, non-planar clipping surface. The surface is used to generate a
    volume mask to hide voxels on the other side of the mask.
    """

    ICON_PATH: str = "ui/graphics/icon_smooth_surface.png"
    INITIAL_LABEL: str = "Clipping Spline"
    INITIAL_CHECK_STATE: Qt.CheckState = Qt.Unchecked  # type: ignore
    UI_SETTINGS_CLASS = Ui_SettingsClippingSpline

    def __init__(self,
                 error_reporter: ErrorReporter,
                 view_frame: ViewFrame,
                 timeline: Timeline,
                 camera: Camera) -> None:
        super().__init__()
        self.error_reporter = error_reporter
        self.view_frame = view_frame
        self.timeline = timeline
        self.camera = camera
        self.initialized: bool = False
        self.mask: VolumeMaskTPS = VolumeMaskTPS()
        self.mask_updater: MaskUpdater = MaskUpdater(self.mask, view_frame)
        self.bounds: Optional[ImageBounds] = None
        self.regularization_filter: Optional[EditDoneEventFilter] = None

    def add_to_scene_list(self, scene_list: Optional[QListWidget]) -> None:
        """Make a list widget item and adds it to the scene list.

        Although scene_list is marked as optional to conform with the
        SceneItem super class, None is not a legal type.
        """

        super().add_to_scene_list(scene_list)
        assert scene_list is not None, "scene_list cannot be None."
        self.scene_list = scene_list

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        super()._update_ui()
        self.ui_settings.select_variable.setCurrentIndex(
            2 * self.mask.axis + int(self.mask.keep_greater_than)
        )
        if self.initialized:
            self.ui_settings.button_initialize.setText("Uninitialize")
        else:
            self.ui_settings.button_initialize.setText("Initialize")
        self.ui_settings.edit_regularization.setText(
            nice_exp_format(f"{self.mask.regularization:.4g}")
        )
        self.ui_settings.checkbox_mesh.setCheckState(
            Qt.Checked if self.mask_updater.show_mesh else Qt.Unchecked  # type: ignore
        )

    def update_visibility(self, view_frame: ViewFrame) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        super().update_visibility(view_frame)
        self.attach_mask()

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        super().bind_event_listeners(view_frame)

        def change_variable() -> None:
            index = self.ui_settings.select_variable.currentIndex()
            self.mask.set_axis(index // 2)
            self.mask.set_direction(bool(index % 2))
            logger.info(f"Axis: {self.mask.axis}, GT: {self.mask.keep_greater_than}")
            self.update_view()
            self.attach_mask()

        self.ui_settings.select_variable.currentIndexChanged.connect(
            change_variable
        )

        def toggle_initialization() -> None:
            if self.initialized:
                self._uninitialize_mask()
            else:
                self.initialize_mask()
        self.ui_settings.button_initialize.clicked.connect(toggle_initialization)

        def change_regularization() -> None:
            self.mask.set_regularization(validate_float(
                self.ui_settings.edit_regularization.text(),
                0., float("inf")
            ))
            self.update_view()
            self.attach_mask()

        self.regularization_filter = EditDoneEventFilter(change_regularization)
        self.ui_settings.edit_regularization.installEventFilter(
            self.regularization_filter
        )

        def toggle_mesh(state: Qt.CheckState) -> None:
            self.mask_updater.show_mesh = state == Qt.Checked  # type: ignore
            self.attach_mask()

        self.ui_settings.checkbox_mesh.stateChanged.connect(toggle_mesh)

    def update_bounds(self, bounds: ImageBounds) -> None:
        """Update all the bounds on the control point VTK plane widgets."""

        self.bounds = bounds
        for point in self.mask.control_points:
            point.place(bounds)

    def add_ctrl_pt(self, origin: Optional[Vec3] = None) -> None:
        """Create a new control point and add it to the scene view."""

        name = f"Control Point {self.mask.count_cp() + 1}"
        if not origin:
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
        row = self.scene_list.row(self.list_widget)
        point = ControlPoint(name, origin, self.view_frame, self)
        point.scene_list_insert(self.scene_list, row + 1)
        if self.bounds is not None:
            point.place(self.bounds)
        self.scene_list.setCurrentItem(point.list_widget)
        self.mask.add_cp(point)
        self.attach_mask()

    def delete_ctrl_pt(self, point: ControlPoint) -> None:
        """Remove the passed control point from the list and the scene view."""

        if self.mask.count_cp() <= 3 and self.initialized:
            # An active spline can't have fewer than 3 control points.
            self._uninitialize_mask()

        point.remove_from_scene_list(self.scene_list)
        self.mask.delete_cp(point)
        self.attach_mask()

    def attach_mask(self, volume: Optional[VolumeImage] = None) -> Optional[Thread]:
        """Start a thread to build and attach the mask to the viewer.

        Returns the thread so the caller can track progress, if applicable.

        This runs on either the VolumeUpdater or UI thread, so it offloads
        the heavy computation to the MaskUpdater thread. This is also
        important because the VolumeUpdater thread heavily utilizes the disk
        while the mask utilizes the processor; separating the two allows
        efficient use of both resources simultaneously.
        """

        # If a volume was given, then this was passed by the VolumeUpdater
        # and it will render it for us, otherwise, we render it here.
        do_render: bool = volume is None

        if volume is not None:
            self.mask.set_volume(volume)

        if self.checked and self.initialized:
            assert self.mask.has_volume(), "Initialized without a volume somehow."
            # The volume exists when the VolumeUpdater triggers this method.
            # In that case, it will handle rendering for us.
            return self.mask_updater.queue(do_render)

        self.mask_updater.clear_mask()
        logger.info("Cleared mask")
        if do_render:
            logger.debug("attach_mask:VTK_render()")
            self.view_frame.vtk_render()
        return None

    def initialize_mask(self) -> None:
        """Initialize the VolumeMaskTPS object.

        Runs on the UI thread; no expensive operations are allowable.

        When "add_points" is True, new points will be added until at least three
        points exist to form a plane.
        """

        # TODO: Initialization is now meaningless.

        # Can only decide how to allocate resources if volumes exist.
        if not self.mask.has_volume():
            self.error_reporter.illegal_action("The mask can only be initialized when a volume is present.")
            return

        logger.info("Initializing.")

        # Make sure there are at least 3 control points.
        for i in range(max(0, 3 - self.mask.count_cp())):
            self.add_ctrl_pt()

        self.initialized = True
        self.update_view()
        self.attach_mask()

    def _uninitialize_mask(self) -> None:
        """Uninitialize the VolumeMaskTPS object."""

        # TODO: Is there ever a reason to do this? It's meaningless now.

        logger.info("Uninitializing.")
        self.mask.free()
        self.initialized = False
        self.update_view()
        self.attach_mask()

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "ClippingSpline"
        struct["axis"] = self.mask.axis
        struct["keep_greater_than"] = self.mask.keep_greater_than
        struct["smoothing"] = self.mask.regularization
        struct["show_mesh"] = self.mask_updater.show_mesh
        struct["initialized"] = self.initialized
        return struct

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
        self.mask_updater.show_mesh = show_mesh

        if self.initialized and not initialized:
            self._uninitialize_mask()
        elif not self.initialized and initialized and self.mask.has_volume():
            # I think it's appropriate here to silently ignore the error when initialization is impossible.
            self.initialize_mask()
        else:
            self.update_view()
            self.attach_mask()

        return []
