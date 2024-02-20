import logging
import math
from typing import (
    Any,
    Optional,
)

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

from animation.asceneitems.asceneitem import ASceneItem
from sceneitems.sceneitem import load_float, load_bool
from validatenumericinput import (
    nice_exp_format,
)

logger = logging.getLogger(__name__)


class AScaleBar(ASceneItem):
    """Stores the scale bar widget and manages its UI data."""

    INITIAL_CHECK_STATE: Optional[bool] = True

    def __init__(self, renderer: vtkRenderer) -> None:
        super().__init__()
        self.renderer: vtkRenderer = renderer

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

    def update_visibility(self) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        self.actor.SetVisibility(self.checked)
        self.label_actor.SetVisibility(self.checked and self.show_label)

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        width_microns = load_float("width_microns", struct, errors, min_=1e-36)
        show_label = load_bool("show_label", struct, errors)

        if len(errors) > 0:
            return errors

        self.width = width_microns
        self.show_label = show_label
        return []
