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
from typing import Optional

from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor

from animation.asceneitems.aplanecontroller import APlaneController
from sceneitems.sceneitem import Vec3

logger = logging.getLogger(__name__)


class AClippingPlane(APlaneController):
    """Stores the VTK plane widget and manages its UI data."""

    INITIAL_CHECK_STATE: Optional[bool] = False

    def __init__(self, interactor: vtkGenericRenderWindowInteractor) -> None:
        origin = Vec3(0, 0, 0)
        normal = Vec3(1, 1, 0)
        super().__init__(interactor, origin, normal)
