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
    Iterator,
    NamedTuple,
    Optional,
)

from PyQt5.QtGui import QColor
from vtkmodules.vtkCommonDataModel import vtkPiecewiseFunction
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction

from animation.asceneitems.asceneitem import ASceneItem
from animation.aview import AView
from sceneitems.sceneitem import (
    load_bool,
    load_color,
    load_int,
    load_vec,
)

logger = logging.getLogger(__name__)

# These are the upper-bound colors used for different channel IDs by default.
DEFAULT_CHANNEL_COLORS: list[QColor] = [
    QColor(0xffffff),  # 0: White (default)
    QColor(0xff7f00),  # 1: Orange (triangular)
    QColor(0xff0000),  # 2: Red
    QColor(0x00ff00),  # 3: Green
    QColor(0xff00ff),  # 4: Purple
    QColor(0xffff00),  # 5: Yellow
    QColor(0x00ffff),  # 6: Cyan
    # ... All subsequent colors are color 0.
]


class TransferFuncPoint(NamedTuple):
    """Represents a point shared between the opacity and color functions.

    I.e.:
      opacity(x) = o
      rgb_color(x) = (c[0], c[1], c[2])
    """

    x: float  # Independent variable
    o: float  # Dependent opacity
    c: tuple[float, float, float]  # Dependent color


class AImageChannel(ASceneItem):
    """Represents one of the color channels of a volume image.

    Manages the transfer function.
    """

    INITIAL_CHECK_STATE: Optional[bool] = True

    def __init__(self, channel_id: int) -> None:
        super().__init__()
        # This ID is a zero-based index.
        self.channel_id: int = channel_id

        # All other channels default to linear.
        self.triangular: bool = channel_id == 1
        self.opacity0: float = 0.
        self.opacity1: float = 0.25
        if self.triangular:
            self.range0: float = 0.01
            self.range1: float = 0.45
        else:
            self.range0 = 40 / 255
            self.range1 = 130 / 255

        # Lower range defaults to blue for triangular, black for linear.
        self.color0: QColor = QColor(0, 0, 255 * int(self.triangular))
        # The center is always black by default.
        self.color1: QColor = QColor(0x000000)
        # We choose the
        if channel_id < len(DEFAULT_CHANNEL_COLORS):
            i_default_color = channel_id
        else:
            i_default_color = 0
        self.color2: QColor = DEFAULT_CHANNEL_COLORS[i_default_color]

        self.scalar_range: tuple[float, float] = (0., 1.)
        self.exists: bool = False

    def update_visibility(self, view_frame: AView) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        self.update_v_prop(view_frame)

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

    def update_v_prop(self, view_frame: AView) -> None:
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
                x_full = (b - a) * (x_norm - a)
                logger.debug(f"Adding point, x={x_full}, o={o}, c={c}")
                otf.AddPoint(x_full, o)
                ctf.AddRGBPoint(x_full, *c)
            v_prop.SetColor(self.channel_id, ctf)
        else:
            logger.debug(f"Clearing channel #{self.channel_id}")
            # Full transparency.
            otf.AddPoint(0, 0)
        v_prop.SetScalarOpacity(self.channel_id, otf)

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        channel_id = load_int("channel_id", struct, errors)
        assert channel_id == self.channel_id, \
            f"Loaded a channel to the wrong ID. Was {channel_id}, should be {self.channel_id}."
        triangular = load_bool("triangular", struct, errors)
        opacity = load_vec("opacity", 2, struct, errors, min_=0, max_=1)
        dynamic_range = load_vec("dynamic_range", 2, struct, errors, min_=0, max_=1)
        color_low = load_color("color_low", struct, errors)
        color_center = load_color("color_center", struct, errors)
        color_high = load_color("color_high", struct, errors)

        if len(errors) > 0:
            return errors

        self.triangular = triangular
        self.opacity0, self.opacity1 = opacity
        self.range0, self.range1 = dynamic_range
        self.color0 = color_low
        self.color1 = color_center
        self.color2 = color_high
        self.update_view()
        return []
