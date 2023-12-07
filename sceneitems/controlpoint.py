import logging
from typing import (
    Any,
    TYPE_CHECKING,
)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QListWidget,
    QWidget,
)
from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkFiltersSources import vtkSphereSource
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)

from sceneitems.planecontroller import PlaneController
from sceneitems.sceneitem import Vec3
from viewframe import ViewFrame

if TYPE_CHECKING:
    from clippingspline import ClippingSpline

logger = logging.getLogger(__name__)


class ControlPoint(PlaneController):
    """Stores the VTK plane widget and manages its UI data.

    This is like a clipping plane, but it doesn't actually clip; it is
    instead intended for use with a smooth clipper.
    """

    ICON_PATH: str = "ui/graphics/icon_control_point.png"
    INITIAL_CHECK_STATE: Qt.CheckState = Qt.Checked  # type: ignore

    def __init__(self,
                 name: str,
                 origin: Vec3,
                 view_frame: ViewFrame,
                 clipping_spline: "ClippingSpline") -> None:
        self.view_frame: ViewFrame = view_frame
        self.clipping_spline: "ClippingSpline" = clipping_spline
        self.sphere_source = vtkSphereSource()
        self.sphere_source.SetRadius(15)  # Units of microns.
        self.sphere_mapper = vtkPolyDataMapper()
        self.sphere_mapper.SetInputConnection(self.sphere_source.GetOutputPort())
        self.sphere_actor = vtkActor()
        self.sphere_actor.SetMapper(self.sphere_mapper)
        self.sphere_actor.GetProperty().SetColor(0, 1, 0)  # Green.
        self.sphere_actor.PickableOn()
        view_frame.renderer.AddActor(self.sphere_actor)

        def on_pick(*_: Any) -> None:
            """Called when the sphere indicator is clicked, or "picked".

            Can be used as a VTK event callback. The arguments are ignored.
            """

            self.scene_list.setCurrentItem(self.list_widget)
            logger.info("Picked.")

        self.sphere_actor.AddObserver(
            vtkCommand.PickEvent,
            on_pick
        )

        normal = Vec3(0, 1, 0)
        super().__init__(name, view_frame.interactor, clipping_spline.camera,
                         origin, normal)

        def on_interact(*_: Any) -> None:
            """Called when the plane is manipulated.

            Can be used as a VTK event callback. The arguments are ignored.
            """

            self.update_view()
            self.sphere_source.SetCenter(self.get_origin())
            self.clipping_spline.mask.update_cp(self)
            self.clipping_spline.attach_mask()

        self.i_plane.AddObserver(
            vtkCommand.EndInteractionEvent,
            on_interact
        )

    def scene_list_insert(self, scene_list: QListWidget, row: int) -> None:
        """Make a list widget item and inserts it into the scene list at row."""

        self.add_to_scene_list(None)
        scene_list.insertItem(row, self.list_widget)
        self.scene_list = scene_list

    def make_settings_widget(self) -> QWidget:
        """Create a widget to fill the scene settings field."""

        widget = super().make_settings_widget()
        self.ui_settings.button_new_plane.setText("+ New Point")
        self.ui_settings.button_delete_plane.setText("Delete Point")

        # When a control point is selected, it needs to become non-selectable.
        # Control points are automatically selected upon creation.
        self.view_frame.set_pickable_actors([
            cp.sphere_actor
            for cp in self.clipping_spline.mask.control_points
            if cp is not self
        ])

        return widget

    def remove_from_scene_list(self, scene_list: QListWidget) -> None:
        """Remove the list item widget from the scene list."""

        super().remove_from_scene_list(scene_list)
        self.view_frame.renderer.RemoveActor(self.sphere_actor)

    def update_visibility(self, view_frame: ViewFrame) -> None:
        """Check the checkbox state and decide whether to show or hide."""

        super().update_visibility(view_frame)
        self.sphere_actor.SetVisibility(self.checked)

    def deselect(self) -> None:
        """Hide the VTK widget for controlling the plane."""

        super().deselect()
        self.view_frame.add_pickable_actor(self.sphere_actor)

    def bind_event_listeners(self, view_frame: ViewFrame) -> None:
        """Creates and attaches an event handler to all the settings."""

        super().bind_event_listeners(view_frame)

        def on_delete(_: Any = None) -> None:
            self.clipping_spline.delete_ctrl_pt(self)
        self.ui_settings.button_delete_plane.clicked.connect(on_delete)
        self.ui_settings.button_new_plane.clicked.connect(
            self.clipping_spline.add_ctrl_pt
        )

    def _input_origin(self) -> None:
        """Called when the normal is set in the UI line edits."""

        super()._input_origin()
        self.clipping_spline.mask.update_cp(self)
        self.clipping_spline.attach_mask()

    def set_origin(self, origin: Vec3) -> None:
        """Set the origin of the VTK implicit plane."""

        super().set_origin(origin)
        self.sphere_source.SetCenter(origin)

    def to_struct(self) -> dict[str, Any]:
        """Create a serializable structure containing all the data."""

        struct = super().to_struct()
        struct["type"] = "ControlPoint"
        return struct
