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
    Callable,
    Iterator,
    NamedTuple,
    Optional,
    TYPE_CHECKING,
)

import numpy as np
import numpy.typing as npt
from PyQt5.QtCore import (
    Qt,
    QPoint,
    QRectF,
)
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QColorDialog,
    QGraphicsScene,
    QGraphicsItem,
    QListWidget,
    QStyleOptionGraphicsItem,
    QWidget,
)
from vtkmodules.vtkCommonDataModel import vtkPiecewiseFunction
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction

from main.bundleutil import GFX_DIR
from main.eventfilter import (
    EditDoneEventFilter,
    MOUSE_WHEEL_EVENT_FILTER,
)
if TYPE_CHECKING:
    from main.scene import Scene
from main.validatenumericinput import (
    nice_exp_format,
    validate_float,
)
from main.viewframe import ViewFrame
from sceneitems.sceneitem import (
    SceneItem,
    load_bool,
    load_color,
    load_int,
    load_str,
    load_vec,
)
from ui.settings_channel import Ui_SettingsChannel

logger = logging.getLogger(__name__)

# These are the upper-bound colors used for different channel IDs by default.
DEFAULT_LINEAR_CHANNEL_COLORS: list[QColor] = [
    QColor(0xffffff),  # 0: White (default)
    QColor(0xff0000),  # 1: Red
    QColor(0x00ff00),  # 2: Green
    QColor(0x0000ff),  # 3: Blue
    QColor(0xff00ff),  # 4: Magenta
    QColor(0xffff00),  # 5: Yellow
    QColor(0x00ffff),  # 6: Cyan
    # ... All subsequent colors rotate through the cycle.
]

DEFAULT_TRIANGULAR_CHANNEL_COLORS: list[tuple[QColor, QColor]] = [
    (QColor(0x00ffff), QColor(0xff00ff)),  # 0: Cyan -> Magenta
    (QColor(0x0000ff), QColor(0xff7f00)),  # 1: Blue -> Orange
    (QColor(0x00ff00), QColor(0xffff00)),  # 2: Green -> Yellow
    (QColor(0x007fff), QColor(0xff0000)),  # 3: Marine -> Red
    # ... All subsequent colors rotate through the cycle.
]

# Constant used to distinguish between the histogram of an ordinary linear
# channel and that of a triangular channel. This is an experimental value.
# Typical values for a triangular channel seem to cluster around -0.98, while
# linear tends to range more broadly from 0.15 to 0.99.
LINEAR_SPREAD_ESTIMATE_THRESHOLD: float = -0.5
# These represent thresholds which work well enough for computing the dynamic
# range cutoffs. They essentially represent the fraction of pixels to saturate
# at the lower and upper ends of the range, respectively. The lower bound is
# much larger so that a nice transparency effect can be achieved.
LOW_HISTOGRAM_THRESHOLD: float = 0.3
HIGH_HISTOGRAM_THRESHOLD: float = 1e-4


class TransferFuncPoint(NamedTuple):
    """Represents a point shared between the opacity and color functions.

    I.e.:
      opacity(x) = o
      rgb_color(x) = (c[0], c[1], c[2])
    """

    x: float  # Independent variable
    o: float  # Dependent opacity
    c: tuple[float, float, float]  # Dependent color


class PolylineItem(QGraphicsItem):
    """For drawing a polyline in a QGraphicsScene with a default line style."""

    PEN: QPen = QPen(Qt.black, 4, Qt.SolidLine, Qt.RoundCap)  # type: ignore

    def __init__(self) -> None:
        super().__init__()
        self.points: list[tuple[float, float]] = []
        self.size: Optional[tuple[int, int]] = None

    def paint(self,
              painter: QPainter,
              option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        """Method override called when the item needs to be redrawn."""

        if len(self.points) == 0:
            return

        assert widget is not None
        w = widget.width()
        h = widget.height()
        self.size = (w, h)

        polygon = QPolygonF()
        for p in self.points:
            polygon.append(QPoint(int(p[0] * w - w / 2), int(h / 2 - p[1] * h)))
        painter.setPen(PolylineItem.PEN)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPolyline(polygon)

    def boundingRect(self) -> QRectF:
        """Abstract method override yielding the object bounds."""

        if self.size is None:
            return QRectF(0, 0, 0, 0)
        return QRectF(0, 0, self.size[0], self.size[1])


class ImageChannel(SceneItem):
    """Represents one of the color channels of a volume image.

    Manages the transfer function.
    """

    ICON_PATH: str = GFX_DIR + "/icon_channel.png"
    INITIAL_CHECK_STATE: Qt.CheckState = Qt.Checked  # type: ignore
    UI_SETTINGS_CLASS = Ui_SettingsChannel

    def __init__(self, channel_id: int, scene: "Scene") -> None:
        super().__init__()
        # This ID is a zero-based index.
        self.channel_id: int = channel_id
        self.scene: "Scene" = scene

        self.name: str = ""
        self.INITIAL_LABEL = self._get_label()

        # All other channels default to linear.
        self.triangular: bool = False
        self.opacity0: float = 0.
        self.opacity1: float = 0.25
        self.range0: float = 0.
        self.range1: float = 1.
        self.color0: QColor = QColor(0x000000)
        self.color1: QColor = QColor(0x000000)
        self.color2: QColor = DEFAULT_LINEAR_CHANNEL_COLORS[
            channel_id % len(DEFAULT_LINEAR_CHANNEL_COLORS)]

        self.scalar_range: tuple[float, float] = (0., 1.)
        self.exists: bool = False

        self.transfer_func_item: PolylineItem = PolylineItem()
        self.graphics_scene: QGraphicsScene = QGraphicsScene()
        self.graphics_scene.addItem(self.transfer_func_item)

        self.edit_filter_name: Optional[EditDoneEventFilter] = None
        self.edit_opacity0_filter: Optional[EditDoneEventFilter] = None
        self.edit_opacity1_filter: Optional[EditDoneEventFilter] = None
        self.edit_range0_filter: Optional[EditDoneEventFilter] = None
        self.edit_range1_filter: Optional[EditDoneEventFilter] = None

    def add_to_scene_list(self, scene_list: Optional[QListWidget]) -> None:
        """Make a list widget item and adds it to the scene list."""

        super().add_to_scene_list(scene_list)
        self.update_item_label()
        self.exists = True

    def scene_list_insert(self, scene_list: QListWidget, row: int) -> None:
        """Make a list widget item and inserts it into the scene list at row."""

        self.add_to_scene_list(None)
        scene_list.insertItem(row, self.list_widget)
        self.scene_list = scene_list

    def remove_from_scene_list(self, scene_list: QListWidget) -> None:
        """Remove the list item widget from the scene list."""

        super().remove_from_scene_list(scene_list)
        self.exists = False

    def update_visibility(self, view_frame: ViewFrame) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        super().update_visibility(view_frame)
        self.update_v_prop(view_frame)

    def make_settings_widget(self) -> QWidget:
        """Create a widget to fill the scene settings field.

        Called when this object is selected and becomes active.
        """

        settings_widget = super().make_settings_widget()
        self.ui_settings.select_transfer_func.installEventFilter(
            MOUSE_WHEEL_EVENT_FILTER
        )
        self.ui_settings.graphic_transfer_func.setScene(self.graphics_scene)
        return settings_widget

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        super()._update_ui()
        ui = self.ui_settings
        ui.label_channel_ID.setText(f"Channel {self.channel_id + 1}:")
        ui.item_name.setText(self.name)
        ui.select_transfer_func.setCurrentIndex(int(self.triangular))
        ui.edit_opacity0.setText(nice_exp_format(f"{100 * self.opacity0:g}"))
        ui.edit_opacity1.setText(nice_exp_format(f"{100 * self.opacity1:g}"))
        ui.edit_range0.setText(nice_exp_format(f"{100 * self.range0:g}"))
        ui.edit_range1.setText(nice_exp_format(f"{100 * self.range1:g}"))
        ui.label_color0.setText(self.color0.name())
        ui.label_color1.setText(self.color1.name())
        ui.label_color2.setText(self.color2.name())
        # Set the color picker button labels to a block showing the color.
        pix_map = QPixmap(16, 16)
        pix_map.fill(self.color0)
        ui.button_color0.setIcon(QIcon(pix_map))
        pix_map.fill(self.color1)
        ui.button_color1.setIcon(QIcon(pix_map))
        pix_map.fill(self.color2)
        ui.button_color2.setIcon(QIcon(pix_map))

        # Draw the transfer function in the graphics area.
        tf = self._make_transfer_func()
        points = [(a.x, a.o) for a in tf]
        points.insert(0, (0, points[0][1]))
        points.append((1, points[-1][1]))
        self.transfer_func_item.points = points
        self.graphics_scene.update()

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings.

        The handler will be called when any individual item is modified,
        triggering the VTK window to update with the new volume settings.
        """

        super().bind_event_listeners(view_frame)
        ui = self.ui_settings

        def update_name() -> None:
            """Update the name box."""
            self.name = ui.item_name.text()
            self.update_item_label()

        self.edit_filter_name = EditDoneEventFilter(update_name)
        ui.item_name.installEventFilter(self.edit_filter_name)

        def on_delete(_: Any = None) -> None:
            self.scene.delete_channel(self)

        self.ui_settings.button_delete_chan.clicked.connect(on_delete)
        self.ui_settings.button_new_chan.clicked.connect(self.scene.new_channel)

        def on_tf_type_changed(index: int) -> None:
            assert 0 <= index <= 1, f"Invalid combo box index selected: {index}"
            self.triangular = bool(index)
            self.update_view()
            self.update_v_prop(view_frame)
            logger.debug("on_TF_type_changed:VTK_render()")
            view_frame.vtk_render()

        ui.select_transfer_func.currentIndexChanged.connect(
            on_tf_type_changed
        )

        def read_opacity0() -> None:
            self.opacity0 = validate_float(ui.edit_opacity0.text(), 0, 100) / 100
            self.update_view()
            self.update_v_prop(view_frame)
            logger.debug("read_opacity0:VTK_render()")
            view_frame.vtk_render()

        def read_opacity1() -> None:
            self.opacity1 = validate_float(ui.edit_opacity1.text(), 0, 100) / 100
            self.update_view()
            self.update_v_prop(view_frame)
            logger.debug("read_opacity1:VTK_render()")
            view_frame.vtk_render()

        self.edit_opacity0_filter = EditDoneEventFilter(read_opacity0)
        self.edit_opacity1_filter = EditDoneEventFilter(read_opacity1)
        ui.edit_opacity0.installEventFilter(self.edit_opacity0_filter)
        ui.edit_opacity1.installEventFilter(self.edit_opacity1_filter)

        def read_range0() -> None:
            self.range0 = validate_float(ui.edit_range0.text(),
                                         0, 100 * self.range1) / 100
            self.update_view()
            self.update_v_prop(view_frame)
            logger.debug("read_range0:VTK_render()")
            view_frame.vtk_render()

        def read_range1() -> None:
            self.range1 = validate_float(ui.edit_range1.text(),
                                         100 * self.range0, 100) / 100
            self.update_view()
            self.update_v_prop(view_frame)
            logger.debug("read_range1:VTK_render()")
            view_frame.vtk_render()

        self.edit_range0_filter = EditDoneEventFilter(read_range0)
        self.edit_range1_filter = EditDoneEventFilter(read_range1)
        ui.edit_range0.installEventFilter(self.edit_range0_filter)
        ui.edit_range1.installEventFilter(self.edit_range1_filter)

        def make_color_callback(var: str, alias: str) -> Callable[[Any], None]:
            def set_color(_: Any = None) -> None:
                setattr(self, var, QColorDialog.getColor(
                    getattr(self, var),  # Initial color
                    None,  # Parent widget
                    f"Select {alias} Color"  # Popup title
                ))
                self.update_view()
                self.update_v_prop(view_frame)
                logger.debug(f"set_{var}:VTK_render()")
                view_frame.vtk_render()

            return set_color

        ui.button_color0.clicked.connect(make_color_callback("color0", "Lower"))
        ui.button_color1.clicked.connect(make_color_callback("color1", "Central"))
        ui.button_color2.clicked.connect(make_color_callback("color2", "Upper"))

    def update_item_label(self):
        """Set the list widget label to match the plane's name."""

        self.list_widget.setText(self._get_label())

    def _get_label(self) -> str:
        """Create the appropriate label for this item."""

        if self.name:
            return f"Ch.{self.channel_id + 1}: {self.name}"
        return f"Channel {self.channel_id + 1}"

    def _make_transfer_func(self) -> Iterator[TransferFuncPoint]:
        """Make the list of points that define a VTK transfer function.

        All values range from [0, 1]. This method assumes that the color and
        opacity transfer functions share an independent variable.
        """

        rgb0 = self.color0.getRgbF()[:3]
        rgb1 = self.color1.getRgbF()[:3]
        rgb2 = self.color2.getRgbF()[:3]
        if self.triangular:
            x = [(1 - self.range1) / 2, (1 - self.range0) / 2,
                 (1 + self.range0) / 2, (1 + self.range1) / 2]
            o = [self.opacity1, self.opacity0,
                 self.opacity0, self.opacity1]
            c = [rgb0, rgb1, rgb1, rgb2]
        else:
            x = [self.range0, self.range1]
            o = [self.opacity0, self.opacity1]
            c = [rgb0, rgb2]
        logger.debug(f"Transfer function: x={x}, o={o}, c={c}")
        # noinspection PyTypeChecker
        return map(TransferFuncPoint, x, o, c)

    def update_v_prop(self, view_frame: ViewFrame) -> None:
        """Copy the settings to VTK's volume property in the ViewFrame.

        When this channel doesn't exist in the scene list, make the channel
        fully transparent.
        """

        v_prop = view_frame.v_prop
        logger.debug(f"Update V-prop channel #{self.channel_id}.")

        # Opacity transfer function
        otf = vtkPiecewiseFunction()
        otf.AllowDuplicateScalarsOn()
        if self.exists and self.checked:
            ctf = vtkColorTransferFunction()
            ctf.AllowDuplicateScalarsOn()
            a, b = self.scalar_range
            for x_norm, o, c in self._make_transfer_func():
                # Expand x to the full range.
                x_full = a + (b - a) * x_norm
                logger.debug(f"Adding point, x={x_full}, o={o}, c={c}")
                otf.AddPoint(x_full, o)
                ctf.AddRGBPoint(x_full, *c)
            v_prop.SetColor(self.channel_id, ctf)
        else:
            logger.debug(f"Clearing channel #{self.channel_id}")
            # Full transparency.
            otf.AddPoint(0, 0)
        v_prop.SetScalarOpacity(self.channel_id, otf)

    def from_histogram(self, histogram: npt.NDArray[np.int64]) -> None:
        """Use the histogram from a channel of the volume image to distinguish
        linear vs. triangular, compute the dynamic range, and update the colors.

        Linear vs. triangular is determined by measuring the spread from the
        center of the histogram.
        """

        x = abs(np.linspace(-2, 2, histogram.size)) - 1
        spread_estimate = (x * histogram).sum() / histogram.sum()
        logger.debug("The histogram spread estimate for channel "
                     f"{self.channel_id} was {spread_estimate}")
        if spread_estimate > LINEAR_SPREAD_ESTIMATE_THRESHOLD:
            self._from_histogram_linear(histogram)
        else:
            self._from_histogram_triangular(histogram)
        if self.range0 >= self.range1:
            logger.info("Dynamic range analysis failed; defaulting to [0-1]")
            self.range0 = 0.0
            self.range1 = 1.0
        self.update_view()

    def _from_histogram_linear(self, histogram: npt.NDArray[np.int64]) -> None:
        """Compute the dynamic range for a linear histogram.

        The dynamic range is chosen to have a predefined fraction of saturated
        pixels on the upper and lower ends, assuming low values are transparent.
        Colors are updated if this channel used to be triangular.
        """

        s: int = histogram.size
        # Skip the first bin since histograms often contain many zeros
        # which shouldn't be counted as part of the valid image.
        n: int = histogram[1:].sum()
        i: int = 0
        sum_low: int = 0
        for i in range(1, s):
            sum_low += histogram[i]
            if sum_low > n*LOW_HISTOGRAM_THRESHOLD:
                break
        self.range0 = round(i / (s - 1), 6)

        sum_high: int = 0
        for i in reversed(range(s)):
            sum_high += histogram[i]
            if sum_high > n*HIGH_HISTOGRAM_THRESHOLD:
                break
        self.range1 = round(i / (s - 1), 6)

        if not self.triangular:
            return
        logger.debug(f"Linear channel {self.channel_id} was triangular; setting colors.")
        self.triangular = False
        self.color0 = QColor(0x000000)
        self.color1 = QColor(0x000000)
        self.color2 = DEFAULT_LINEAR_CHANNEL_COLORS[
            self.channel_id % len(DEFAULT_LINEAR_CHANNEL_COLORS)]

    def _from_histogram_triangular(self, histogram: npt.NDArray[np.int64]) -> None:
        """Compute the dynamic range for a triangular histogram.

        The dynamic range is chosen to have a predefined fraction of saturated
        pixels on the outer and inner ends, assuming low values are transparent.
        Colors are updated if this channel used to be linear.
        """

        s: int = histogram.size
        # The middle one (odd histogram) or two (even) samples are the zero samples.
        n: int = histogram.sum() - histogram[s // 2]
        if s % 2 == 0:
            n -= histogram[s // 2 - 1]
        i: int = 0
        sum_inner: int = 0
        for i in range(1, s//2):
            sum_inner += histogram[s//2 + i]
            sum_inner += histogram[s//2-1 - i]
            if sum_inner > n*LOW_HISTOGRAM_THRESHOLD:
                break
        self.range0 = round(i/(s//2 - 1), 6)

        sum_outer: int = 0
        for i in range(s//2):
            sum_outer += histogram[i]
            sum_outer += histogram[s-1 - i]
            if sum_outer > n*HIGH_HISTOGRAM_THRESHOLD:
                break
        self.range1 = round(1 - i/(s//2 - 1), 6)

        if self.triangular:
            return
        logger.debug(f"Triangular channel {self.channel_id} was linear; setting colors.")
        self.triangular = True
        self.color1 = QColor(0x000000)
        self.color0, self.color2 = DEFAULT_TRIANGULAR_CHANNEL_COLORS[
            self.channel_id % len(DEFAULT_TRIANGULAR_CHANNEL_COLORS)]

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "ImageChannel"
        struct["channel_id"] = self.channel_id
        struct["name"] = self.name
        struct["triangular"] = self.triangular
        struct["opacity"] = (self.opacity0, self.opacity1)
        struct["dynamic_range"] = (self.range0, self.range1)
        struct["color_low"] = self.color0.name()
        struct["color_center"] = self.color1.name()
        struct["color_high"] = self.color2.name()
        return struct

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        channel_id = load_int("channel_id", struct, errors)
        assert channel_id == self.channel_id, \
            f"Loaded a channel to the wrong ID. Was {channel_id}, should be {self.channel_id}."
        name = load_str("name", struct, errors)
        triangular = load_bool("triangular", struct, errors)
        opacity = load_vec("opacity", 2, struct, errors, min_=0, max_=1)
        dynamic_range = load_vec("dynamic_range", 2, struct, errors, min_=0, max_=1)
        color_low = load_color("color_low", struct, errors)
        color_center = load_color("color_center", struct, errors)
        color_high = load_color("color_high", struct, errors)

        if len(errors) > 0:
            return errors

        self.name = name
        self.triangular = triangular
        self.opacity0, self.opacity1 = opacity
        self.range0, self.range1 = dynamic_range
        self.color0 = color_low
        self.color1 = color_center
        self.color2 = color_high
        self.update_view()
        return []
