from typing import Optional

from vtkmodules.vtkCommonCore import vtkPoints, vtkFloatArray
from vtkmodules.vtkCommonDataModel import (
    vtkCellArray,
    vtkPolyData,
    vtkPolygon,
)
from vtkmodules.vtkIOImage import vtkImageReader, vtkImageReader2Factory
from vtkmodules.vtkRenderingCore import (
    vtkActor2D,
    vtkPolyDataMapper2D,
    vtkRenderer,
    vtkTextActor,
    vtkTextProperty,
    vtkTexture,
    vtkTexturedActor2D,
)


class Annotation:
    actor: vtkActor2D or vtkTextActor or vtkTexturedActor2D

    def attach(self, renderer: vtkRenderer) -> None:
        renderer.AddActor2D(self.actor)

    def detach(self, renderer: vtkRenderer) -> None:
        renderer.RemoveActor(self.actor)


class TextStyle:
    CENTER: int = 1
    LEFT: int = 0
    RIGHT: int = 2
    BOTTOM: int = 0
    TOP: int = 2

    def __init__(self):
        self.property = vtkTextProperty()
        self.font_size(24)
        # self.font_family("Arial")
        # self.color(1., 1., 1.)

    def font_size(self, point: int) -> None:
        self.property.SetFontSize(point)

    def font(self, name: str) -> None:
        self.property.SetFontFamilyAsString(name)

    def align(self, horizontal: int, vertical: int) -> None:
        self.property.SetJustification(horizontal)
        self.property.SetVerticalJustification(vertical)

    def bold(self, bold: bool) -> None:
        self.property.SetBold(bold)

    def italic(self, italic: bool) -> None:
        self.property.SetItalic(italic)

    def color(self, red: float, green: float, blue: float) -> None:
        """Color values range [0-1]. Default is white."""

        self.property.SetColor(red, green, blue)

    def background_color(self, red: float, green: float, blue: float) -> None:
        self.property.SetBackgroundColor(red, green, blue)

    def opacity(self, opacity: float) -> None:
        self.property.SetOpacity(opacity)

    def background_opacity(self, opacity: float) -> None:
        self.property.SetBackgroundOpacity(opacity)

    def angle(self, degrees_ccw: float) -> None:
        self.property.SetOrientation(degrees_ccw)


class TextAnnotation(Annotation):
    def __init__(
            self,
            text: str,
            position: tuple[float, float],
            style: Optional[TextStyle] = None):
        self.actor = vtkTextActor()
        if style is not None:
            self.actor.SetTextProperty(style.property)
        self.position: tuple[float, float] = position
        self.actor.SetInput(text)

    def attach(self, renderer: vtkRenderer) -> None:
        window_size = renderer.GetSize()
        self.actor.SetPosition(
            self.position[0] * window_size[0],
            self.position[1] * window_size[1])
        super().attach(renderer)


class ImageAnnotation(Annotation):
    def __init__(
            self,
            image_path: str,
            bounds: tuple[float, float, float, float],
            opacity: float = 1.):
        super().__init__()

        factory = vtkImageReader2Factory()
        self.reader = factory.CreateImageReader2(image_path)
        self.reader.SetFileName(image_path)

        self.texture = vtkTexture()
        self.texture.InterpolateOn()
        self.texture.SetInputConnection(self.reader.GetOutputPort())

        self.polygon = vtkPolygon()
        point_ids = self.polygon.GetPointIds()
        for i in range(4):
            point_ids.InsertNextId(i)
        self.poly_array = vtkCellArray()
        self.poly_array.InsertNextCell(self.polygon)
        self.poly_data = vtkPolyData()
        self.poly_data.SetPolys(self.poly_array)

        self.mapper = vtkPolyDataMapper2D()
        self.mapper.SetInputData(self.poly_data)

        self.actor = vtkTexturedActor2D()
        self.actor.SetTexture(self.texture)
        self.actor.SetMapper(self.mapper)
        self.actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        disp_prop = self.actor.GetProperty()
        disp_prop.SetDisplayLocationToForeground()
        disp_prop.SetOpacity(opacity)
        disp_prop.SetColor(1., 1., 1.)

        self.bounds = bounds

    def attach(self, renderer: vtkRenderer) -> None:
        window_size = renderer.GetSize()
        bounds = [self.bounds[i] * window_size[i % 2] for i in range(4)]
        points = vtkPoints()
        points.InsertNextPoint([bounds[0], bounds[1], 0])                          # Bottom left
        points.InsertNextPoint([bounds[0] + bounds[2], bounds[1], 0])              # Bottom right
        points.InsertNextPoint([bounds[0] + bounds[2], bounds[1] + bounds[3], 0])  # Top right
        points.InsertNextPoint([bounds[0], bounds[1] + bounds[3], 0])              # Top left
        self.poly_data.SetPoints(points)

        # Set the texture coordinates for each vertex
        tex_coords = vtkFloatArray()
        tex_coords.SetNumberOfComponents(2)
        tex_coords.InsertNextTuple2(0., 0.)
        tex_coords.InsertNextTuple2(1., 0.)
        tex_coords.InsertNextTuple2(1., 1.)
        tex_coords.InsertNextTuple2(0., 1.)
        self.poly_data.GetPointData().SetTCoords(tex_coords)

        self.poly_data.Modified()

        super().attach(renderer)
