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

import json
import logging
import os
from threading import Thread
from typing import (
    Any,
    Callable,
    Optional,
)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QListWidgetItem,
    QWidget,
)
from vtkmodules.vtkCommonCore import vtkCommand
from vtkmodules.vtkCommonDataModel import vtkPlaneCollection
from vtkmodules.vtkRenderingVolume import vtkVolumePicker

from main.errorreporter import (
    ErrorReporter,
    FileError,
)
from main.eventfilter import ResizeEventFilter
from main.timeline import Timeline
from main.viewframe import ViewFrame
from main.volumeimage import (
    ImageBounds,
    VolumeImage,
)
from sceneitems.camera import Camera
from sceneitems.clippingplane import ClippingPlane
from sceneitems.clippingspline import ClippingSpline
from sceneitems.controlpoint import ControlPoint
from sceneitems.imagechannel import ImageChannel
from sceneitems.orientationmarker import OrientationMarker
from sceneitems.planecontroller import PlaneController
from sceneitems.scalebar import ScaleBar
from sceneitems.sceneitem import SceneItem, load_int, Vec3
from ui.main_window import Ui_MainWindow

logger = logging.getLogger(__name__)

# VTK can support up to this many clipping planes active at once.
# This is a fundamental limit imposed by OpenGL.
MAX_ACTIVE_PLANES: int = 6
# VTK can support up to this many unique image channels.
MAX_CHANNELS: int = 4


def tree_apply(tree: list[Any], func: Callable[[Any], None]) -> None:
    """Walk tree and apply func to each leaf.

    Tree is a list of either elements or other trees.
    """

    for leaf in tree:
        if type(leaf) is list:
            tree_apply(leaf, func)
        else:
            func(leaf)


class Scene:
    """Stores many types of objects related to the 3D view.

    A scene list contains one camera object for manipulating the view, a
    scale bar, a gimbal, a smooth clipper with any number of control
    points, and an unlimited number of clipping planes. It also contains
    the volume settings object, but this is not part of the list. The
    scene is able to write and read itself from a file by calling the
    serialize and deserialize methods on each of its elements.
    """

    def __init__(
            self,
            error_reporter: ErrorReporter,
            ui: Ui_MainWindow,
            view_frame: ViewFrame,
            timeline: Timeline) -> None:
        self.error_reporter: ErrorReporter = error_reporter
        self.ui: Ui_MainWindow = ui
        self.view_frame: ViewFrame = view_frame
        self.bounds: Optional[ImageBounds] = None
        self.n_active_planes: int = 0
        self.resize_event_filter: Optional[ResizeEventFilter] = None
        self.last_save_path: str = ""
        self.last_keyframe_path: str = ""
        self.last_volume: Optional[VolumeImage] = None
        self.channel_adjustment_thread: Optional[Thread] = None

        # Make all the possible channels, but only list one initially.
        self.image_channels: list[ImageChannel] = [
            ImageChannel(i, self) for i in range(MAX_CHANNELS)
        ]
        self.scale_bar = ScaleBar(error_reporter, view_frame.renderer, timeline)
        self.camera = Camera(view_frame, self.scale_bar)
        self.orientation_marker = OrientationMarker(view_frame.interactor)
        self.clipping_spline = ClippingSpline(error_reporter, view_frame, timeline, self.camera)
        self.planes: list[ClippingPlane] = [
            ClippingPlane("Plane 1", view_frame.interactor, self)
        ]

    def initialize_scene_list(self) -> None:
        """Add all the scene items to the scene list in the correct order."""

        all_items = [
            self.camera,
            self.image_channels[:1],
            self.scale_bar,
            self.orientation_marker,
            self.clipping_spline,
            self.planes
        ]
        tree_apply(all_items, lambda a: a.add_to_scene_list(self.ui.scene_list))

    def bind_event_listeners(self) -> None:
        """Attach all the UI elements to their respective functions.

        This only applies to always-visible widgets. Elements in the
        settings panel need to be bound and unbound each time the user
        navigates to its respective item.
        """

        self.ui.scene_list.currentItemChanged.connect(self._on_item_select)
        self.ui.scene_list.itemChanged.connect(self._on_item_changed)
        self.view_frame.interactor.AddObserver(
            vtkCommand.EndInteractionEvent,
            self.camera.update_view
        )
        self.resize_event_filter = ResizeEventFilter(self.scale_bar.update_view)
        self.ui.frame_vtk.installEventFilter(self.resize_event_filter)

        def on_delete_item(_: bool = False) -> None:
            item: Optional[QListWidgetItem] = self.ui.scene_list.currentItem()
            if item is None:
                return
            scene_item = item.scene_item
            if type(scene_item) is ImageChannel:
                self.delete_channel(scene_item)
            elif type(scene_item) is ClippingPlane:
                self.delete_plane(scene_item)
            elif type(scene_item) is ControlPoint:
                self.clipping_spline.delete_ctrl_pt(scene_item)

        self.ui.action_delete_item.triggered.connect(on_delete_item)
        self.ui.action_delete_item.setShortcut("Delete")

        def on_deselect_item(_: bool = False) -> None:
            self.ui.scene_list.setCurrentItem(None)

        self.ui.action_deselect_item.triggered.connect(on_deselect_item)
        self.ui.action_deselect_item.setShortcut("Escape")

        def on_toggle_item(_: bool = False) -> None:
            item: Optional[QListWidgetItem] = self.ui.scene_list.currentItem()
            if item is None:
                logger.debug("No scene item selected to toggle.")
                return
            if not (item.flags() & Qt.ItemIsUserCheckable):
                logger.debug("Scene item cannot be toggled.")
                return
            scene_item: SceneItem = item.scene_item
            scene_item.set_checked(not scene_item.checked)
            logger.debug("Scene item toggled.")

        self.ui.action_toggle_item.triggered.connect(on_toggle_item)
        self.ui.action_toggle_item.setShortcut("Ctrl+H")

        def on_look_at_plane(_: bool = False) -> None:
            item: Optional[QListWidgetItem] = self.ui.scene_list.currentItem()
            if item is None:
                return
            scene_item: SceneItem = item.scene_item
            if issubclass(type(scene_item), PlaneController):
                scene_item.look_at(self.view_frame)

        self.ui.action_look_at_plane.triggered.connect(on_look_at_plane)
        self.ui.action_look_at_plane.setShortcut("Ctrl+L")

        def on_plane_to_view(_: bool = False) -> None:
            item: Optional[QListWidgetItem] = self.ui.scene_list.currentItem()
            if item is None:
                return
            scene_item: SceneItem = item.scene_item
            if issubclass(type(scene_item), PlaneController):
                scene_item.normal_to_view()

        self.ui.action_plane_to_view.triggered.connect(on_plane_to_view)
        self.ui.action_plane_to_view.setShortcut("Ctrl+P")

        volume_picker: vtkVolumePicker = vtkVolumePicker()

        def on_place_control_point(_: bool = False) -> None:
            click_pos: tuple[int, int] = self.view_frame.interactor.GetEventPosition()
            success: int = volume_picker.Pick(*click_pos, 0, self.view_frame.renderer)
            if success:
                pos: tuple[float, float, float] = volume_picker.GetPickPosition()
                self.clipping_spline.add_ctrl_pt(Vec3(*pos))

        self.ui.action_place_control_point.triggered.connect(on_place_control_point)
        self.ui.action_place_control_point.setShortcut("P")

        self.ui.action_adjust_channels.triggered.connect(self.start_adjust_channels)
        self.ui.action_adjust_channels.setShortcut("Ctrl+E")

    def start_adjust_channels(self, _: bool = False) -> None:
        """Update the channel display ranges to match the histogram of the
        currently visible volume.

        Compute the histogram in a new thread, since that might take a while,
        and is usually called from the UI thread. Returns without starting a new
        thread if a previous thread is already running.
        """

        v: VolumeImage = self.last_volume
        if v is None:
            logger.debug("Cannot adjust channels because there is no volume.")
            return
        if (self.channel_adjustment_thread is not None
                and self.channel_adjustment_thread.is_alive()):
            logger.debug("A channel adjuster is already running. Abort!")
            return
        logger.debug("Starting a new channel adjustment thread.")
        self.channel_adjustment_thread = Thread(target=self._adjust_channels,
                                                args=(v,))
        self.channel_adjustment_thread.start()

    def _adjust_channels(self, v: VolumeImage) -> None:
        """Update the channel display ranges to match the histogram of a volume."""

        for i_chan in range(v.n_channels()):
            chan: ImageChannel = self.image_channels[i_chan]
            chan.from_histogram(v.histogram(i_chan))
            if not chan.exists:
                self.new_channel()
            elif chan.checked:
                chan.update_v_prop(self.view_frame)
            else:
                # Calls `chan.update_v_prop` indirectly.
                chan.set_checked(True)
        # Render again just in case it hasn't happened already.
        logger.debug("_adjust_channels:VTK_render()")
        self.view_frame.vtk_render()

    def _on_item_select(
            self,
            new_item: QListWidgetItem,
            old_item: QListWidgetItem) -> None:
        """React to selection of a list item by filling in the settings area.

        The settings area is filled with the widget produced by the scene
        element selected.
        """

        # The UI initializes with an empty widget by default, so you can
        # usually destroy it, but at some point, this caused a crash. It's
        # unclear how the widget became None.
        old_widget = self.ui.scene_scroller.takeWidget()
        if old_widget is not None:
            old_widget.destroy()
        else:
            logger.debug("The scene scroller lost its widget somehow!")

        # No race condition; this runs on the UI thread.
        for i in range(self.ui.scene_list.count()):
            item = self.ui.scene_list.item(i)
            if item is old_item:
                item.scene_item.deselect()
                break
        else:
            logger.info("No item deselected.")

        for i in range(self.ui.scene_list.count()):
            item = self.ui.scene_list.item(i)
            if item is new_item:
                widget = item.scene_item.make_settings_widget()
                item.scene_item.bind_event_listeners(self.view_frame)
                break
        else:
            logger.info("No item selected.")
            widget = QWidget()
        self.ui.scene_scroller.setWidget(widget)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """React to checking or unchecking of list items."""

        logger.info(f"On item changed: {item.scene_item.INITIAL_LABEL}")  # type: ignore

        # Handle items which are not clipping planes.
        for i in range(self.ui.scene_list.count()):
            list_item = self.ui.scene_list.item(i)
            if list_item is item:
                if type(list_item.scene_item) is ClippingPlane:
                    break
                list_item.scene_item.update_visibility(self.view_frame)
                logger.debug("_on_item_changed:VTK_render()")
                self.view_frame.vtk_render()
        else:
            # `item` isn't a clipping plane, so no further treatment is necessary.
            return

        # `item` is a clipping plane.
        plane = list_item.scene_item
        now_checked = plane.list_widget.checkState() == Qt.Checked  # type: ignore
        if plane.checked == now_checked:
            # The action was not a check/uncheck action.
            return

        # A plane was checked.
        delta_active = int(now_checked) - int(plane.checked)
        self.n_active_planes += delta_active
        plane.checked = not plane.checked
        self.update_clipping_planes()

        # We need to grey out the unchecked checkboxes when the limit of
        # visible clipping planes is reached, and vice versa when under the
        # limit.
        if self.n_active_planes == MAX_ACTIVE_PLANES:
            # Disable checking for unchecked planes to prevent exceeding the limit.
            self.disable_plane_checking()
        elif self.n_active_planes == MAX_ACTIVE_PLANES + delta_active:
            # Checking was disabled, so re-enable checking for all planes.
            self.enable_plane_checking()

    def enable_plane_checking(self) -> None:
        """Re-enable checking for unchecked planes when under the limit."""

        for plane in self.planes:
            plane.list_widget.setFlags(
                plane.list_widget.flags()
                | Qt.ItemIsUserCheckable  # type: ignore
            )

    def disable_plane_checking(self) -> None:
        """Disable checking for unchecked planes to prevent exceeding the limit."""

        for plane in self.planes:
            if not plane.checked:
                plane.list_widget.setFlags(
                    plane.list_widget.flags()
                    & ~Qt.ItemIsUserCheckable  # type: ignore
                )

    def update_clipping_planes(self, *_: Any) -> None:
        """Set the active clipping planes in the VTK volume mapper.

        This can be used as a callback when the clipping plane widget is
        moved, in which case it is passed a vtkImplicitPlaneWidget and the
        string, "InteractionEvent", as arguments, which are ignored.
        """

        logger.info("update_clipping_planes")

        vtk_planes = vtkPlaneCollection()
        n = 0
        for plane in self.planes:
            # Limit the number of possible clipping planes active at once to
            # prevent an error from occurring.
            if plane.checked:  # type: ignore
                n += 1
                assert n <= MAX_ACTIVE_PLANES, "Clipping plane limit exceeded."
                vtk_plane = plane.get_vtk_plane()
                vtk_planes.AddItem(vtk_plane)
        self.view_frame.v_mapper.SetClippingPlanes(vtk_planes)
        logger.debug("update_clipping_planes:VTK_render()")
        self.view_frame.vtk_render()

    def new_plane(self) -> None:
        """Create a new default plane and add it to the scene."""

        # It's OK to have duplicate plane names, so don't worry too much
        # about the default name.
        plane = ClippingPlane(
            f"Plane {len(self.planes) + 1}",
            self.view_frame.interactor,
            self)
        self.planes.append(plane)
        plane.add_to_scene_list(self.ui.scene_list)
        if self.bounds is not None:
            plane.place(self.bounds)
        self.ui.scene_list.setCurrentItem(plane.list_widget)

        if self.n_active_planes == MAX_ACTIVE_PLANES:
            self.disable_plane_checking()

    def delete_plane(self, plane: ClippingPlane) -> None:
        """Remove the passed plane from the scene."""

        # Refuse to delete the last plane. Otherwise, it will be impossible
        # for the user to add a new plane ever again.
        if len(self.planes) <= 1:
            self.error_reporter.illegal_action("You can't delete your last clipping plane; \
you'll have no way to get another!")
            return

        if plane.checked:
            self.n_active_planes -= 1
            self.enable_plane_checking()

        # The plane does not need to be deselected since the event handler
        # will process that for us, but doing it twice is safe just in case.
        plane.deselect()
        self.planes.remove(plane)
        row = self.ui.scene_list.row(plane.list_widget)
        self.ui.scene_list.takeItem(row)
        self.update_clipping_planes()

    def new_channel(self) -> None:
        """Create a new default image channel and add it to the scene.

        Maintains self.image_channels as sorted by channel_id.
        """

        # Find the index corresponding to the first free channel ID.
        for i, chan in enumerate(self.image_channels):
            if not chan.exists:
                break
        else:
            # All possible channels have been added already.
            self.error_reporter.illegal_action(f"{MAX_CHANNELS} image channels is the maximum number \
permitted by the visualization toolkit (VTK).")
            return

        # There will always be at least one existing channel to insert this one relative to.
        if i > 0:
            # An existing channel is behind: Insert after the previous element.
            prev_chan = self.image_channels[i - 1]
            row = 1 + self.ui.scene_list.row(prev_chan.list_widget)
        else:
            # An existing channel is in front: Insert before the next element.
            for next_chan in self.image_channels[i + 1:]:
                if next_chan.exists:
                    break
            else:
                raise RuntimeError("How is it possible that no channel exists?")
            row = self.ui.scene_list.row(next_chan.list_widget)
        chan.scene_list_insert(self.ui.scene_list, row)
        self.ui.scene_list.setCurrentItem(chan.list_widget)
        chan.set_checked(True)
        chan.update_v_prop(self.view_frame)
        logger.debug("new_channel:VTK_render()")
        self.view_frame.vtk_render()

    def delete_channel(self, chan: ImageChannel) -> None:
        """Remove the passed image channel from the scene."""

        # Refuse to delete the last channel. Otherwise, it will be
        # impossible for the user to add a new channel ever again.
        n_exist = sum(int(chan.exists) for chan in self.image_channels)
        if n_exist <= 1:
            self.error_reporter.illegal_action("You can't delete your last image channel; \
you'll have no way to get another!")
            return

        chan.remove_from_scene_list(self.ui.scene_list)
        chan.update_v_prop(self.view_frame)
        logger.debug("delete_channel:VTK_render()")
        self.view_frame.vtk_render()

    def on_timeline_loaded(self, timeline: Timeline) -> None:
        """Called by MainWindow when timeline has new volumes."""

        self.camera.on_timeline_loaded(timeline)
        self.last_volume = timeline.get()
        self.start_adjust_channels()

    def volume_update(self, volume: VolumeImage) -> None:
        """Called whenever the active volume is replaced."""

        self.last_volume = volume
        self.bounds = volume.bounds()
        scalar_range = volume.get_scalar_range()
        logger.debug(f"Volume, bound={self.bounds}, range={scalar_range}")
        for chan in self.image_channels:
            chan.scalar_range = scalar_range
            chan.update_v_prop(self.view_frame)
        for plane in self.planes:
            plane.place(self.bounds)
        self.clipping_spline.update_bounds(self.bounds)

    def attach_mask(self, volume: VolumeImage) -> Optional[Thread]:
        """Attach a volume mask to the VTK mapper if needed.

        This runs on the VolumeUpdater thread, so expensive operations are
        allowed and won't lag the UI thread.
        """

        return self.clipping_spline.attach_mask(volume)

    def to_struct(self, keyframe: bool = False) -> list[dict[str, Any]]:
        """Create a serializable structure containing all the scene item data.

        When "keyframe" is true, the scene_struct includes only scene items that have
        been flagged as "save_keyframes", and additional keyframe data is included.
        """

        struct: list[dict[str, Any]] = []

        if keyframe:
            # Keyframes need some additional data about the volume.
            if self.last_volume is None:
                group_index = None
                time_index = None
                n_times = None
            else:
                group_index = self.last_volume.group_index
                time_index = self.last_volume.time_index
                n_times = self.last_volume.n_times
            struct.append({
                "type": "VolumeInfo",
                "group_index": group_index,
                "time_index": time_index,
                "n_times": n_times,
            })

        for i in range(self.ui.scene_list.count()):
            item: SceneItem = self.ui.scene_list.item(i).scene_item
            if not keyframe or item.save_keyframes:
                struct.append(item.to_struct())
        return struct

    def from_struct(self, scene_struct: list[dict[str, Any]]) -> list[str]:
        """Reconstructs the scene items based on the data given in scene_struct.

        Updates all the changed widgets when done and returns any errors
        that may have occurred while decoding.
        """

        logger.debug("From struct.")

        # Always clear the current scene item selection so we don't need to
        # worry about potential complications.
        self.ui.scene_list.setCurrentItem(None)

        if type(scene_struct) is not list:
            return [f"Scene should be a list of items, not {type(scene_struct)}"]

        # Unique element such as the Camera shouldn't exist more than once.
        encountered: set[str] = set()
        errors: list[str] = []
        new_planes: list[ClippingPlane] = []
        new_cps: list[ControlPoint] = []
        new_channels: list[bool] = [False] * MAX_CHANNELS
        new_clipping_spline_struct: Optional[Any] = None
        # Now all of those new objects need to be reinitialized from the scene_struct.
        for item_struct in scene_struct:
            if type(item_struct) is not dict:
                errors.append(f"Scene items must be objects, not {type(item_struct)}")
                continue
            t = item_struct["type"]
            if t in encountered and t in ["VolumeInfo", "Camera", "ScaleBar",
                                          "OrientationMarker", "ClippingSpline"]:
                errors.append(f"Multiple counts of {t} in scene file")
                continue
            if t == "VolumeInfo":
                pass  # This data exists only for keyframes; don't load it.
            elif t == "Camera":
                err = self.camera.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    self.camera.update_interp(self.view_frame)
            elif t == "ScaleBar":
                err = self.scale_bar.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    self.scale_bar.update_visibility(self.view_frame)
            elif t == "OrientationMarker":
                errors.extend(self.orientation_marker.from_struct(item_struct))
            elif t == "ClippingSpline":
                # Defer this until after the control points are done so
                # initialization can happen correctly.
                new_clipping_spline_struct = item_struct
            elif t == "ControlPoint":
                item = ControlPoint("", Vec3(0., 0., 0.), self.view_frame, self.clipping_spline)
                err = item.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    new_cps.append(item)
            elif t == "ClippingPlane":
                item = ClippingPlane("", self.view_frame.interactor, self)
                err = item.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    new_planes.append(item)
            elif t == "ImageChannel":
                channel_id = load_int("channel_id", item_struct, errors, min_=0, max_=MAX_CHANNELS - 1)
                if channel_id is None:
                    continue
                if new_channels[channel_id]:
                    errors.append(f"Multiple counts of {t} #{channel_id} in scene file")
                item = self.image_channels[channel_id]
                err = item.from_struct(item_struct)
                if err:
                    errors.extend(err)
                else:
                    new_channels[channel_id] = True
            else:
                errors.append(f"Unrecognized item type: '{t}'")
                continue
            encountered.add(t)

        self.camera.update_view()
        self.scale_bar.update_view()

        # Set up all the image channels. Leave any existing channel items where
        # they are, and put any new channel items after the last item removed.
        if any(new_channels):
            row: int = -1
            for i, chan in enumerate(self.image_channels):
                # Make the new channels exist and the old channels not,
                # but only update them if necessary.
                if chan.exists:
                    row = self.ui.scene_list.row(chan.list_widget)
                    if new_channels[i]:
                        chan.update_item_label()
                    else:
                        chan.remove_from_scene_list(self.ui.scene_list)
                elif new_channels[i]:
                    row += 1
                    chan.scene_list_insert(self.ui.scene_list, row)
                chan.update_v_prop(self.view_frame)

        # Set up all the clipping planes.
        if new_planes:
            # Only clear the existing set of planes if at least one
            # plane exists in the scene file.
            for plane in self.planes:
                plane.remove_from_scene_list(self.ui.scene_list)
            self.planes = []
            self.n_active_planes = 0
            for plane in new_planes:
                if self.n_active_planes < MAX_ACTIVE_PLANES:
                    self.n_active_planes += int(plane.checked)
                else:
                    errors.append(f"Too many planes simultaneously active ({MAX_ACTIVE_PLANES} allowed)")
                    plane.set_checked(False)
                self.planes.append(plane)
                plane.add_to_scene_list(self.ui.scene_list)
                if self.bounds is not None:
                    plane.place(self.bounds)
            if self.n_active_planes == MAX_ACTIVE_PLANES:
                self.disable_plane_checking()
            logger.debug("Added planes.")
            self.update_clipping_planes()

        # Set up the clipping spline and all its control points.
        if new_cps:
            # Remove old control points.
            for cp in reversed(self.clipping_spline.mask.control_points):
                cp.remove_from_scene_list(self.ui.scene_list)
                self.clipping_spline.mask.delete_cp(cp)

            # Insert new control points after the clipping spline, starting
            # with the last so the order is preserved.
            row = self.ui.scene_list.row(self.clipping_spline.list_widget)
            for cp in reversed(new_cps):
                cp.scene_list_insert(self.ui.scene_list, row + 1)
                if self.bounds is not None:
                    cp.place(self.bounds)
                self.clipping_spline.mask.add_cp(cp)
                cp.update_visibility(self.view_frame)

            # Reset the list of pickable actors for control points.
            # This would be problematic if a control point were currently selected.
            self.view_frame.set_pickable_actors([
                cp.sphere_actor
                for cp in self.clipping_spline.mask.control_points
            ])

        if new_clipping_spline_struct is None:
            self.clipping_spline.attach_mask()
        else:
            errors.extend(self.clipping_spline.from_struct(new_clipping_spline_struct))

        logger.debug("from_struct:VTK_render()")
        self.view_frame.vtk_render()
        return errors

    def default_keyframe_path(self, cwd: str = ".") -> str:
        """Find the best guess for the next keyframe path.

        Keyframes are usually named like dir_path/kf_saved-name_xxxx.json
        When the user specifies an unusual name, try to match it.

        :param cwd: The current working directory to use as a default when the
            directory is otherwise unknown.
        """

        if self.last_keyframe_path:
            root, file_name = os.path.split(self.last_keyframe_path)
            file_name_l = file_name.lower()
            if file_name_l.endswith(".json"):
                file_name = file_name[:-len(".json")]
            name_parts = file_name.split("_")
            kf_i = -1
            try:
                kf_i = int(name_parts[-1])
                name_parts = name_parts[:-1]
            except (IndexError, ValueError):
                pass
            if kf_i < 0:  # int(...) might give a negative number.
                return self.last_keyframe_path
            kf_i += 1
            name_parts.append(f"{kf_i:04d}.json")
            return os.path.join(root, "_".join(name_parts))
        if self.last_save_path:
            root, file_name = os.path.split(self.last_save_path)
            file_name_l = file_name.lower()
            if file_name_l.endswith(".json"):
                file_name = file_name[:-len(".json")]
            if file_name_l.startswith("kf_"):
                file_name = file_name[len("kf_"):]
            name_parts = file_name.split("_")
            kf_i = -1
            try:
                kf_i = int(name_parts[-1])
                name_parts = name_parts[:-1]
            except (IndexError, ValueError):
                pass
            kf_i = max(0, kf_i + 1)
            name_parts = ["kf"] + name_parts + [f"{kf_i:04d}.json"]
            return os.path.join(root, "_".join(name_parts))
        return os.path.join(cwd, "kf_0.json")

    def save_to_file(self, path: str = "", keyframe: bool = False) -> None:
        """Write the scene data to the file specified at path.

        Reports an error to the user when file write fails.

        When "keyframe" is True, save the file as a keyframe rather than an
        ordinary scene.
        """

        if keyframe:
            self.last_keyframe_path = path
        elif path:  # Save as.
            self.last_save_path = path
            self.last_keyframe_path = ""
        else:  # Regular save.
            path = self.last_save_path
        assert path, "Tried to save with no path specified."

        try:
            with open(path, "w") as file:
                json.dump(self.to_struct(keyframe), file, indent="\t", sort_keys=True)
        except OSError as e:
            self.error_reporter.file_errors([
                FileError(f"Unable to write file: {e}", path)])

    def load_from_file(self, path: str) -> None:
        """Load the scene data from the file specified at path."""

        self.last_save_path = path
        self.last_keyframe_path = ""

        error_msg: Optional[str] = None
        try:
            with open(path, "r") as file:
                struct = json.load(file)
        except OSError as e:
            error_msg = f"Unable to write file: {e}"
        except json.decoder.JSONDecodeError as e:
            error_msg = f"Malformed JSON file: {e}"
        if error_msg is not None:
            self.error_reporter.file_errors([FileError(error_msg, path)])
            return

        error_msgs: list[str] = self.from_struct(struct)
        if error_msgs:
            self.error_reporter.file_errors([FileError(m, path) for m in error_msgs])
            return
