import logging
from typing import (
    Any,
    Optional,
)

from PyQt5.QtWidgets import QListWidget
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkInteractionWidgets import vtkImplicitPlaneWidget
from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor

from eventfilter import EditDoneEventFilter
from sceneitems.camera import Camera
from sceneitems.sceneitem import (
    SceneItem,
    Vec3, load_str, load_vec,
)
from ui.settings_plane import Ui_SettingsPlane
from validatenumericinput import validate_float_any
from viewframe import ViewFrame
from volumeimage import ImageBounds

logger = logging.getLogger(__name__)


class PlaneController(SceneItem):
    """The generic super-class for elements controlled by a plane widget."""

    UI_SETTINGS_CLASS = Ui_SettingsPlane

    def __init__(self,
                 name: str,
                 interactor: vtkGenericRenderWindowInteractor,
                 camera: Camera,
                 origin: Vec3,
                 normal: Vec3) -> None:
        super().__init__()
        self.INITIAL_LABEL = name
        self.name: str = name
        self.camera: Camera = camera
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

        self.edit_filter_name: Optional[EditDoneEventFilter] = None

        # The plane controller will not be visible until it has been
        # "placed". It cannot be placed until there is a volume with bounds
        # to contain it.
        self.placed: bool = False

    def add_to_scene_list(self, scene_list: Optional[QListWidget]) -> None:
        """Make a list widget item and adds it to the scene list."""

        super().add_to_scene_list(scene_list)
        self.update_item_label()

    def _update_ui(self) -> None:
        """Fill the UI editable fields with information."""

        super()._update_ui()
        if self.placed:
            self.i_plane.EnabledOn()
        self.ui_settings.item_name.setText(self.name)
        plane = self.get_vtk_plane()
        normal = plane.GetNormal()
        origin = plane.GetOrigin()
        self.ui_settings.edit_origin_x.setText(f"{origin[0]:0.1f}")
        self.ui_settings.edit_origin_y.setText(f"{origin[1]:0.1f}")
        self.ui_settings.edit_origin_z.setText(f"{origin[2]:0.1f}")
        self.ui_settings.edit_normal_x.setText(f"{normal[0]:0.3f}")
        self.ui_settings.edit_normal_y.setText(f"{normal[1]:0.3f}")
        self.ui_settings.edit_normal_z.setText(f"{normal[2]:0.3f}")

    def deselect(self) -> None:
        """Hide the VTK widget for controlling the plane."""

        super().deselect()
        if self.placed:
            self.i_plane.EnabledOff()

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        super().bind_event_listeners(view_frame)

        def update_name() -> None:
            """Update the name box."""
            self.name = self.ui_settings.item_name.text()
            self.update_item_label()

        self.edit_filter_name = EditDoneEventFilter(update_name)
        self.ui_settings.item_name.installEventFilter(self.edit_filter_name)

        def on_look_at(_: Any = None):
            self.look_at(view_frame)

        self.ui_settings.button_look_at.clicked.connect(on_look_at)
        self.ui_settings.button_normal_to_view.clicked.connect(self.normal_to_view)

        # Since the origin must lie along the plane and the normal is
        # normalized, it's better if the text boxes don't automatically
        # submit. That would re-normalize the normal before the user is
        # finished editing it.
        self.ui_settings.edit_origin_x.returnPressed.connect(self._input_origin)
        self.ui_settings.edit_origin_y.returnPressed.connect(self._input_origin)
        self.ui_settings.edit_origin_z.returnPressed.connect(self._input_origin)
        self.ui_settings.edit_normal_x.returnPressed.connect(self._input_normal)
        self.ui_settings.edit_normal_y.returnPressed.connect(self._input_normal)
        self.ui_settings.edit_normal_z.returnPressed.connect(self._input_normal)

    def update_item_label(self):
        """Set the list widget label to match the plane's name."""

        self.list_widget.setText(self.name)

    def _input_origin(self) -> None:
        """Called when the normal is set in the UI line edits."""

        x = validate_float_any(self.ui_settings.edit_origin_x.text())
        y = validate_float_any(self.ui_settings.edit_origin_y.text())
        z = validate_float_any(self.ui_settings.edit_origin_z.text())
        self.set_origin(Vec3(x, y, z))
        self.update_view()

    def _input_normal(self) -> None:
        """Called when the normal is set in the UI line edits."""

        # It is OK for the entered normal to be un-normalized.
        x = validate_float_any(self.ui_settings.edit_normal_x.text())
        y = validate_float_any(self.ui_settings.edit_normal_y.text())
        z = validate_float_any(self.ui_settings.edit_normal_z.text())
        self.set_normal(Vec3(x, y, z))
        self.update_view()

    def look_at(self, view_frame: ViewFrame) -> None:
        """Turn the camera to look at the plane origin and match the
        normal."""
        vtk_camera = self.camera.camera
        d = vtk_camera.GetDistance()
        plane = self.get_vtk_plane()
        origin = plane.GetOrigin()
        normal = plane.GetNormal()
        vtk_camera.SetFocalPoint(origin)
        vtk_camera.SetPosition([origin[i] - d * normal[i] for i in range(3)])
        self.camera.update_view()
        logger.debug("look_at:VTK_render()")
        view_frame.vtk_render()

    def normal_to_view(self, _: Any = None) -> None:
        """Turn the plane to point toward the camera."""

        normal = self.camera.camera.GetViewPlaneNormal()
        self.set_normal(Vec3(*(-a for a in normal)))
        self.update_view()

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

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "PlaneController"  # Usually overwritten by the child.
        struct["name"] = self.name
        struct["origin"] = self.get_origin()
        struct["normal"] = self.get_normal()
        return struct

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = super().from_struct(struct)

        name = load_str("name", struct, errors)
        origin = load_vec("origin", 3, struct, errors)
        normal = load_vec("normal", 3, struct, errors)

        if len(errors) > 0:
            return errors

        self.name = name
        self.default_origin: Vec3 = Vec3(*origin)
        self.default_normal: Vec3 = Vec3(*normal)
        self.placed = False

        return []
