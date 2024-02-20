import logging
import math
from typing import (
    Any,
    Callable,
    Optional,
)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from vtkmodules.vtkRenderingCore import vtkCamera

from eventfilter import (
    EditDoneEventFilter,
    MOUSE_WHEEL_EVENT_FILTER,
)
from sceneitems.scalebar import ScaleBar
from sceneitems.sceneitem import (
    SceneItem,
    Vec3,
    load_bool,
    load_float,
    load_vec,
)
from timeline import Timeline
from ui.settings_camera import Ui_SettingsCamera
from validatenumericinput import validate_float_any
from viewframe import ViewFrame

logger = logging.getLogger(__name__)


def _find_view_up(up0: Vec3, axis: int) -> Vec3:
    """Find the new upward-facing vector.

    The new vector is the standard basis vector closest to the original
    while still orthogonal to the axis specified.

    Example:
      _find_view_up(Vec3(0.8, 0.3, -0.1), 0) -> Vec3(0, 1, 0)
    The largest off-axis component is unitized.
    """

    indices = [0, 1, 2]
    del indices[axis]
    up1 = [0., 0., 0.]
    i_largest = max(indices, key=lambda i: abs(up0[i]))
    up1[i_largest] = math.copysign(1, up0[i_largest])
    return Vec3(up1[0], up1[1], up1[2])


class Camera(SceneItem):
    """Stores the VTK camera object and manages its UI data."""

    ICON_PATH: str = "ui/graphics/icon_camera.png"
    INITIAL_LABEL: str = "Camera"
    INITIAL_CHECK_STATE = None
    UI_SETTINGS_CLASS = Ui_SettingsCamera

    def __init__(self, view_frame: ViewFrame, scale_bar: ScaleBar) -> None:
        super().__init__()

        view_frame.renderer.ResetCamera()
        self.camera: vtkCamera = view_frame.renderer.GetActiveCamera()
        self.scale_bar: ScaleBar = scale_bar

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

        self.edit_filter_from: Optional[EditDoneEventFilter] = None
        self.edit_filter_to: Optional[EditDoneEventFilter] = None
        self.edit_filter_roll: Optional[EditDoneEventFilter] = None

        self.linear_interp: bool = True
        view_frame.v_prop.SetInterpolationType(int(self.linear_interp))

    def make_settings_widget(self) -> QWidget:
        """Create a widget to fill the scene settings field."""

        widget = super().make_settings_widget()
        self.ui_settings.select_projection.installEventFilter(
            MOUSE_WHEEL_EVENT_FILTER
        )
        return widget

    def update_view(self, *_: Any) -> None:
        """Fill out visible information in the UI and VTK view port.

        This method might be called when the scroll area is not visible, in
        which case the UI will not be updated.

        This method can also be used as a VTK event callback, in which case
        the arguments are ignored.
        """

        super().update_view()
        self.scale_bar.update_view()

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        super()._update_ui()

        # Where the camera is (from) and where it's looking (to).
        fx, fy, fz = self.camera.GetPosition()
        tx, ty, tz = self.camera.GetFocalPoint()
        roll = self.camera.GetRoll()

        self.ui_settings.edit_from_x.setText(f"{fx:0.1f}")
        self.ui_settings.edit_from_y.setText(f"{fy:0.1f}")
        self.ui_settings.edit_from_z.setText(f"{fz:0.1f}")
        self.ui_settings.edit_to_x.setText(f"{tx:0.1f}")
        self.ui_settings.edit_to_y.setText(f"{ty:0.1f}")
        self.ui_settings.edit_to_z.setText(f"{tz:0.1f}")
        self.ui_settings.edit_roll.setText(f"{roll:0.1f}")

        if self.camera.GetParallelProjection():
            # Orthographic projection.
            self.ui_settings.select_projection.setCurrentIndex(0)
        else:
            # Perspective.
            self.ui_settings.select_projection.setCurrentIndex(1)

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings.

        The handler will be called when any individual item is modified,
        triggering the VTK window to update with the new volume settings.
        """

        super().bind_event_listeners(view_frame)

        def on_roll_plus90(_: Any = None) -> None:
            self.camera.Roll(90)
            self.update_view()
            logger.debug("on_roll_plus90:VTK_render()")
            view_frame.vtk_render()

        self.ui_settings.button_roll_plus90.clicked.connect(on_roll_plus90)

        def on_roll_minus90(_: Any = None) -> None:
            self.camera.Roll(-90)
            self.update_view()
            logger.debug("on_roll_minus90:VTK_render()")
            view_frame.vtk_render()

        self.ui_settings.button_roll_minus90.clicked.connect(on_roll_minus90)

        self.ui_settings.button_x_plus.clicked.connect(
            self._view_from_func(Vec3(1, 0, 0), view_frame))
        self.ui_settings.button_x_minus.clicked.connect(
            self._view_from_func(Vec3(-1, 0, 0), view_frame))
        self.ui_settings.button_y_plus.clicked.connect(
            self._view_from_func(Vec3(0, 1, 0), view_frame))
        self.ui_settings.button_y_minus.clicked.connect(
            self._view_from_func(Vec3(0, -1, 0), view_frame))
        self.ui_settings.button_z_plus.clicked.connect(
            self._view_from_func(Vec3(0, 0, 1), view_frame))
        self.ui_settings.button_z_minus.clicked.connect(
            self._view_from_func(Vec3(0, 0, -1), view_frame))

        def update_position() -> None:
            x = validate_float_any(self.ui_settings.edit_from_x.text())
            y = validate_float_any(self.ui_settings.edit_from_y.text())
            z = validate_float_any(self.ui_settings.edit_from_z.text())
            self.camera.SetPosition(x, y, z)
            self.update_view()
            logger.debug("update_position:VTK_render()")
            view_frame.vtk_render()

        def update_focal_point() -> None:
            x = validate_float_any(self.ui_settings.edit_to_x.text())
            y = validate_float_any(self.ui_settings.edit_to_y.text())
            z = validate_float_any(self.ui_settings.edit_to_z.text())
            self.camera.SetFocalPoint(x, y, z)
            self.update_view()
            logger.debug("update_focal_point:VTK_render()")
            view_frame.vtk_render()

        def update_roll() -> None:
            roll = validate_float_any(self.ui_settings.edit_roll.text())
            roll = (roll + 180) % 360 - 180
            self.camera.SetRoll(roll)
            self.update_view()
            logger.debug("update_roll:VTK_render()")
            view_frame.vtk_render()

        self.edit_filter_from = EditDoneEventFilter(update_position)
        self.edit_filter_to = EditDoneEventFilter(update_focal_point)
        self.edit_filter_roll = EditDoneEventFilter(update_roll)
        self.ui_settings.edit_from_x.installEventFilter(self.edit_filter_from)
        self.ui_settings.edit_from_y.installEventFilter(self.edit_filter_from)
        self.ui_settings.edit_from_z.installEventFilter(self.edit_filter_from)
        self.ui_settings.edit_to_x.installEventFilter(self.edit_filter_to)
        self.ui_settings.edit_to_y.installEventFilter(self.edit_filter_to)
        self.ui_settings.edit_to_z.installEventFilter(self.edit_filter_to)
        self.ui_settings.edit_roll.installEventFilter(self.edit_filter_roll)

        def on_projection_changed(index: int) -> None:
            assert 0 <= index <= 1, f"Invalid projection index selected: {index}"
            if index == 0:
                self.camera.ParallelProjectionOn()
            else:
                self.camera.ParallelProjectionOff()
            logger.debug("on_projection_changed:VTK_render()")
            view_frame.vtk_render()

        self.ui_settings.select_projection.currentIndexChanged.connect(
            on_projection_changed
        )

        def toggle_interp(state: Qt.CheckState) -> None:
            self.linear_interp = state == Qt.Checked  # type: ignore
            self.update_interp(view_frame)
            view_frame.vtk_render()

        self.ui_settings.checkbox_interpolate.stateChanged.connect(toggle_interp)

    def update_interp(self, view_frame: ViewFrame) -> None:
        """Set the VTK interpolation type based on the internal value "linear_interp".

        Must call this after "from_struct" to pass the view frame.
        """

        view_frame.v_prop.SetInterpolationType(int(self.linear_interp))

    def _view_from_func(self,
                        orientation: Vec3,
                        view_frame: ViewFrame) -> Callable[[Any], None]:
        """Create a function to adjust the camera.

        Orientation is a standard basis vector designating the position
        where one would stand if they wanted to view the origin from the
        desired direction.

        The returned function handle will orient the camera from that
        direction looking at the original focal point from the original
        distance.
        """

        assert all([a in [1, 0, -1] for a in orientation]), \
            "Orientation must be a standard basis vector."
        assert 1 == sum([abs(a) for a in orientation]), \
            "Orientation must be a unit length vector."

        # The axis should be the only non-zero value.
        axis = max([0, 1, 2], key=lambda i: abs(orientation[i]))

        def callback(_: Any = None) -> None:
            fp = self.camera.GetFocalPoint()
            d = self.camera.GetDistance()
            up = _find_view_up(self.camera.GetViewUp(), axis)
            self.camera.SetPosition([fp[i] + d * orientation[i] for i in range(3)])
            self.camera.SetViewUp(up)
            self.update_view()
            logger.debug("_view_from:VTK_render()")
            view_frame.vtk_render()

        return callback

    def on_timeline_loaded(self, timeline: Timeline) -> None:
        """Called when a new timeline is loaded to set the camera properly."""

        scale = timeline.get_view_scale()
        self.camera.SetParallelScale(scale)
        self.update_view()

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "Camera"
        struct["position"] = self.camera.GetPosition()
        struct["focal_point"] = self.camera.GetFocalPoint()
        struct["view_up"] = self.camera.GetViewUp()
        struct["scale"] = self.camera.GetParallelScale()
        struct["orthographic"] = bool(self.camera.GetParallelProjection())
        struct["linear_interpolation"] = self.linear_interp
        return struct

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.

        Must call "set_interp" after to finish the initialization.
        """

        errors: list[str] = super().from_struct(struct)

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
        linear_interp = load_bool("linear_interpolation", struct, errors)

        if len(errors) > 0:
            return errors

        self.camera.SetPosition(position)
        self.camera.SetFocalPoint(focal_point)
        if use_view_up:
            # noinspection PyUnboundLocalVariable
            self.camera.SetViewUp(view_up)
        else:
            # noinspection PyUnboundLocalVariable
            self.camera.SetRoll(roll)
        self.camera.SetParallelScale(scale)
        self.camera.SetParallelProjection(orthographic)
        self.linear_interp = linear_interp
        return []
