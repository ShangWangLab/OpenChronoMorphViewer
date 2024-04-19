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
)

from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkInteractionWidgets import vtkImplicitPlaneWidget
from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor

from animation.asceneitems.asceneitem import ASceneItem
from sceneitems.sceneitem import (
    Vec3,
    load_vec,
)
from volumeimage import ImageBounds

logger = logging.getLogger(__name__)


class APlaneController(ASceneItem):
    """The generic super-class for elements controlled by a plane widget."""

    def __init__(self,
                 interactor: vtkGenericRenderWindowInteractor,
                 origin: Vec3,
                 normal: Vec3) -> None:
        super().__init__()
        self.default_origin: Vec3 = origin
        self.default_normal: Vec3 = normal

        self.i_plane = vtkImplicitPlaneWidget()
        self.i_plane.DrawPlaneOff()
        self.i_plane.OutlineTranslationOff()
        self.i_plane.ScaleEnabledOff()
        self.i_plane.SetDiagonalRatio(0.1)
        self.i_plane.SetPlaceFactor(1)
        self.i_plane.SetInteractor(interactor)
        self.set_origin(origin)
        self.set_normal(normal)

        # The plane controller will not be visible until it has been
        # "placed". It cannot be placed until there is a volume with bounds
        # to contain it.
        self.placed: bool = False

    def deselect(self) -> None:
        """Hide the VTK widget for controlling the plane."""

        if self.placed:
            self.i_plane.EnabledOff()

    def place(self, bounds: ImageBounds) -> None:
        """Set the volume bounds of the widget and "place" it."""

        # Placing this widget resets its origin and normal; need to save and
        # reload those values to retain them.
        if not self.placed:
            self.placed = True
            origin = self.default_origin
            normal = self.default_normal
        else:
            plane = self.get_vtk_plane()
            origin = plane.GetOrigin()
            normal = plane.GetNormal()
        self.i_plane.PlaceWidget(bounds)
        self.set_origin(origin)
        self.set_normal(normal)

        logger.info("Placed.")

        # For an unknown reason, when a plane controller already exists and
        # you place this widget on the first-ever volume, you can't run
        # self.i_plane.EnabledOn() right here without getting a VTK error:
        # vtkShaderProgram: Could not create shader object.
        # I think something must be initialized first.

    def get_origin(self) -> Vec3:
        """Return the origin associated with this controller."""

        if self.placed:
            return self.i_plane.GetOrigin()
        return self.default_origin

    def set_origin(self, origin: Vec3) -> None:
        """Set the origin of the VTK implicit plane."""

        # The input needs to be a list to support item assignment. This is a
        # bug in the VTK library.
        self.i_plane.SetOrigin(list(origin))

    def get_normal(self) -> Vec3:
        """Return the normal associated with this controller."""

        if self.placed:
            return self.i_plane.GetNormal()
        return self.default_normal

    def set_normal(self, normal: Vec3) -> None:
        """Set the normal vector of the VTK implicit plane.

        The normal does not need to be unit length."""

        self.i_plane.SetNormal(list(normal))

    def get_vtk_plane(self) -> vtkPlane:
        """Return the plane associated with the implicit VTK plane."""

        plane = vtkPlane()
        self.i_plane.GetPlane(plane)
        return plane

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        origin = load_vec("origin", 3, struct, errors)
        normal = load_vec("normal", 3, struct, errors)

        if len(errors) > 0:
            return errors

        self.default_origin: Vec3 = Vec3(*origin)
        self.default_normal: Vec3 = Vec3(*normal)
        self.placed = False

        return []
