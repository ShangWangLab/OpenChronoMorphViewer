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
