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
import math
from typing import (
    Any,
    Optional,
)

from PyQt5.QtCore import Qt
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkPolygon,
    vtkPolyData,
)
from vtkmodules.vtkRenderingCore import (
    vtkActor2D,
    vtkPolyDataMapper2D,
    vtkRenderer,
    vtkTextActor,
)

from main.errorreporter import ErrorReporter
from main.eventfilter import EditDoneEventFilter
from sceneitems.sceneitem import SceneItem, load_bool, load_float
from main.timeline import Timeline
from ui.settings_scale_bar import Ui_SettingsScaleBar
from main.validatenumericinput import (
    nice_exp_format,
    validate_float,
)
from main.viewframe import ViewFrame

logger = logging.getLogger(__name__)


class ScaleBar(SceneItem):
    """Stores the scale bar widget and manages its UI data."""

    ICON_PATH: str = "ui/graphics/icon_scale_bar.png"
    INITIAL_LABEL: str = "Scale Bar"
    INITIAL_CHECK_STATE: Qt.CheckState = Qt.Unchecked  # type: ignore
    UI_SETTINGS_CLASS = Ui_SettingsScaleBar

    def __init__(self, error_reporter: ErrorReporter, renderer: vtkRenderer, timeline: Timeline) -> None:
        super().__init__()
        self.error_reporter: ErrorReporter = error_reporter
        self.renderer: vtkRenderer = renderer
        self.timeline: Timeline = timeline

        # Define the underlying polygon data.
        self.polygon = vtkPolygon()
        point_ids = self.polygon.GetPointIds()
        for i in range(4):
            point_ids.InsertNextId(i)

        # Set up VTK containers.
        self.poly_array = vtkCellArray()
        self.poly_array.InsertNextCell(self.polygon)
        self.poly_data = vtkPolyData()
        self.poly_data.SetPolys(self.poly_array)

        self.actor = vtkActor2D()
        disp_prop = self.actor.GetProperty()
        disp_prop.SetDisplayLocationToForeground()
        disp_prop.SetColor([1, 1, 1])
        # disp_prop.SetOpacity(0.8)

        # Attach the actor and mapper to the rendering engine.
        self.mapper = vtkPolyDataMapper2D()
        self.mapper.SetInputData(self.poly_data)
        self.actor.SetMapper(self.mapper)

        self.label_actor = vtkTextActor()
        text_prop = self.label_actor.GetTextProperty()
        text_prop.SetJustificationToCentered()
        text_prop.SetVerticalJustificationToBottom()
        text_prop.SetFontSize(16)
        text_prop.BoldOn()

        self.renderer.AddActor2D(self.actor)
        self.renderer.AddActor(self.label_actor)

        self.edit_width: Optional[EditDoneEventFilter] = None
        self.edit_zoom: Optional[EditDoneEventFilter] = None

        self.width: float = 100.  # units, typically microns.
        self.width_px: int = 0
        self.show_label: bool = True

    def _update_vtk(self) -> None:
        """Update information related to the VTK viewport."""

        super()._update_vtk()
        # The units for self.width are microns.
        order = math.floor(math.log10(self.width) / 3)
        # We'll use unit symbols for femto through milli meters.
        # Everything else gets regular meters with an exponent.
        if -3 <= order <= 1:
            display_width = self.width * 10 ** (-3 * order)
            # noinspection SpellCheckingInspection
            prefix = "fpnμm"[order + 3]
        else:
            display_width = self.width * 1e-6
            prefix = ""

        self.label_actor.SetInput(nice_exp_format(f"{display_width:.4g} {prefix}m"))
        self.width_px = self._update_bar()

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        super()._update_ui()
        self.ui_settings.edit_width.setText(nice_exp_format(f"{self.width:.4g}"))
        self.ui_settings.edit_zoom.setText(str(self.width_px))
        self.ui_settings.checkbox_show_label.setChecked(self.show_label)

    def update_visibility(self, view_frame: ViewFrame) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        super().update_visibility(view_frame)
        self.actor.SetVisibility(self.checked)
        self.label_actor.SetVisibility(self.checked and self.show_label)

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        super().bind_event_listeners(view_frame)

        def update_width() -> None:
            """Read and set the width/size of the scale bar."""

            self.width = validate_float(
                self.ui_settings.edit_width.text(),
                1e-36, 1e36
            )
            self.update_view()
            logger.debug("update_width:VTK_render()")
            view_frame.vtk_render()

        self.edit_width = EditDoneEventFilter(update_width)
        self.ui_settings.edit_width.installEventFilter(self.edit_width)

        def update_zoom() -> None:
            """Read and set the zoom of the camera to match the scale bar."""

            camera = self.renderer.GetActiveCamera()
            ren_size = self.renderer.GetSize()
            width_px = validate_float(self.ui_settings.edit_zoom.text(), 0.0, 1e36)
            px_per_micron = width_px / self.width
            scale = ren_size[1] / (2 * px_per_micron)

            # Scale is half the viewport height in microns.
            camera.SetParallelScale(scale)

            self.update_view()
            logger.debug("update_zoom:VTK_render()")
            view_frame.vtk_render()

        self.edit_zoom = EditDoneEventFilter(update_zoom)
        self.ui_settings.edit_zoom.installEventFilter(self.edit_zoom)

        def set_max_resolution(_: Any = None) -> None:
            """Set the camera scale such that the screen resolution matches
            that of the finest volume axis across the whole timeline."""

            if not self.timeline:
                self.error_reporter.illegal_action("Max Resolution finds the finest useful resolution "
                                                   "across all volumes, but no volumes exist.")
                return

            # Scale is half the viewport height in microns.
            # noinspection PyArgumentList
            micron_per_px = self.timeline.min_scale().min()
            ren_size = self.renderer.GetSize()
            scale = micron_per_px * ren_size[1] / 2
            self.renderer.GetActiveCamera().SetParallelScale(scale)

            self.update_view()
            logger.debug("set_max_resolution:VTK_render()")
            view_frame.vtk_render()

        self.ui_settings.button_max_resolution.clicked.connect(set_max_resolution)

        def check_show_label(state: Qt.CheckState) -> None:
            self.show_label = state == Qt.Checked  # type: ignore
            self.update_visibility(view_frame)
            logger.debug("check_show_label:VTK_render()")
            view_frame.vtk_render()

        self.ui_settings.checkbox_show_label.stateChanged.connect(check_show_label)

    def _update_bar(self) -> int:
        """Redraws the scale bar on the screen, returning its width in
        pixels."""

        camera = self.renderer.GetActiveCamera()
        # Scale is half the viewport height in microns.
        scale = camera.GetParallelScale()

        ren_size = self.renderer.GetSize()
        px_per_micron = ren_size[1] / (2 * scale)

        # Offsets from the corner of the screen in pixels.
        ox = 25
        oy = 15
        w = round(self.width * px_per_micron)
        h = 5

        self.points = vtkPoints()
        self.points.InsertNextPoint([ox, oy, 0])  # Bottom left
        self.points.InsertNextPoint([ox + w, oy, 0])  # Bottom right
        self.points.InsertNextPoint([ox + w, oy + h, 0])  # Top right
        self.points.InsertNextPoint([ox, oy + h, 0])  # Top left
        self.poly_data.SetPoints(self.points)
        self.poly_data.Modified()
        self.label_actor.SetPosition(ox + w // 2, 1.5 * oy + h)

        return w

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "ScaleBar"
        struct["width_microns"] = self.width
        struct["show_label"] = self.show_label
        return struct

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        width_microns = load_float("width_microns", struct, errors,
                                   min_=1e-36)
        show_label = load_bool("show_label", struct, errors)

        if len(errors) > 0:
            return errors

        self.width = width_microns
        self.show_label = show_label
        return []
