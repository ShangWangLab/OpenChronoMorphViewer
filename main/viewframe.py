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

import logging
from typing import Optional

from PyQt5.QtCore import (
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
)
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor  # type: ignore
from vtkmodules.vtkCommonCore import vtkCommand, vtkObject
from vtkmodules.vtkIOImage import vtkImageWriter, vtkPNGWriter, vtkJPEGWriter, vtkTIFFWriter
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkActorCollection,
    vtkPropPicker,
    vtkRenderer,
    vtkVolume,
    vtkVolumeProperty, vtkWindowToImageFilter,
)
from vtkmodules.vtkRenderingVolumeOpenGL2 import vtkOpenGLGPUVolumeRayCastMapper

from main.volumeimage import VolumeImage

logger = logging.getLogger(__name__)


class ViewFrame(QFrame):
    """Manages rendering of the 3D volume using the VTK library.

    Contains the vtkRenderer, volume mapper, volume properties, and
    interactor. Basically, most of the core VTK objects. Uses
    multithreading to coordinate rendering operations.
    """

    # This must be defined at the class level to work, yet accessed as a
    # member of the object as 'self._render_signal'. The reason is unknown.
    _render_signal = pyqtSignal()
    _add_actor_signal = pyqtSignal(vtkActor)
    _remove_actor_signal = pyqtSignal(vtkActor)

    def __init__(self, parent: QFrame) -> None:
        super().__init__(parent)

        # Need a handle on the old volume so it doesn't get garbage collected
        # while switching active volumes.
        self._current_volume_image: Optional[VolumeImage] = None

        # Initialize stuff here.
        self._setup_misc_vtk()
        self._setup_interactor()
        self._setup_event_listeners()

        self._render_signal.connect(self._vtk_render_slot)  # type: ignore
        self._add_actor_signal.connect(self._add_actor_slot)  # type: ignore
        self._remove_actor_signal.connect(self._remove_actor_slot)  # type: ignore

    def _setup_misc_vtk(self) -> None:
        """Initialize a bunch of VTK objects."""

        self.v_mapper: vtkOpenGLGPUVolumeRayCastMapper = vtkOpenGLGPUVolumeRayCastMapper()
        self.v_mapper.SetMaskTypeToBinary()
        # These volumes are susceptible to producing a wood-grain artifact
        # when using linear interpolation. This can be mitigated to some
        # degree by applying a random jitter to the sampling function, or by
        # using an irrational sample spacing for the rays on the grid.
        # self.SetAutoAdjustSampleDistances(False)
        # self.v_mapper.SetSampleDistance(0.95492965855)
        self.v_mapper.UseJitteringOn()

        # Volume properties contain things like color mapping and transparency.
        self.v_prop: vtkVolumeProperty = vtkVolumeProperty()

        # This volume stores the 3D volume to be rendered. It is initialized
        # to empty, so it's important to check before attempting to render.
        self.volume: vtkVolume = vtkVolume()
        self.volume.SetMapper(self.v_mapper)
        self.volume.SetProperty(self.v_prop)

        self.renderer: vtkRenderer = vtkRenderer()
        # Black background color.
        self.renderer.SetBackground(0, 0, 0)

    def _setup_interactor(self) -> None:
        """Initialize the VTK interactor and add it to this frame."""

        # Make the actual QtWidget a child so that it can be re-parented.
        self.interactor: QVTKRenderWindowInteractor = QVTKRenderWindowInteractor(self)
        layout: QHBoxLayout = QHBoxLayout()
        layout.addWidget(self.interactor)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        ren_win = self.interactor.GetRenderWindow()
        ren_win.AddRenderer(self.renderer)

    def _setup_event_listeners(self) -> None:
        """Add event observers to allow control points to be picked by clicking
        and disable the default VTK key controls."""

        self.picker: vtkPropPicker = vtkPropPicker()
        self.pickable_actors: vtkActorCollection = vtkActorCollection()

        # noinspection PyUnusedLocal
        def on_char(obj: vtkObject, event: str) -> None:
            """Handle key presses to ignore the default VTK key bindings."""

            logger.debug(f"Key pressed: {self.interactor.GetKeySym()}")
            obj.GetCommand(cmd_id_on_char).AbortFlagOn()

        # noinspection PyUnusedLocal
        def on_left_button_down(obj: vtkObject, event: str) -> None:
            """Handle left clicks to allow picking of control point spheres."""

            if self.pick():
                obj.GetCommand(cmd_id_on_lmbd).AbortFlagOn()

        # Plane widgets have an event priority of 0.5.
        cmd_id_on_char: int = self.interactor.AddObserver(
            vtkCommand.CharEvent, on_char, 0.6)
        cmd_id_on_lmbd: int = self.interactor.AddObserver(
            vtkCommand.LeftButtonPressEvent, on_left_button_down, 0.6)

    def set_pickable_actors(self, actors: list[vtkActor]) -> None:
        """Create the list of actors that can be picked from by left-clicking.

        Intended for picking control points from the clipping spline.
        """

        # noinspection PyAttributeOutsideInit
        self.pickable_actors = vtkActorCollection()
        for a in actors:
            self.pickable_actors.AddItem(a)

    def add_pickable_actor(self, actor: vtkActor) -> None:
        """Add an item to the list of actors that can be picked from by left-clicking."""

        self.pickable_actors.AddItem(actor)

    def pick(self) -> bool:
        """Perform a "pick" operation on the list of pickable actors, returning
        the success/failure state."""

        click_pos: tuple[int, int] = self.interactor.GetEventPosition()
        logger.debug(f"Pick at {click_pos}")
        return self.picker.PickProp(*click_pos, self.renderer, self.pickable_actors)

    def start(self) -> None:
        """Pass the 'start' signal to objects that need it."""

        self.interactor.Initialize()
        self.interactor.Start()

    def set_volume_input(self, volume: VolumeImage) -> None:
        """Sets the VolumeImage given as the volume mapper's input."""

        self.v_mapper.SetInputConnection(
            volume.get_vtk_image().GetOutputPort()
        )
        self._current_volume_image = volume
        logger.debug("Added volume data to mapper.")

    def attach_volume(self) -> None:
        """Verify that the VTK volume has been added to the VTK renderer.

        The volume cannot be added to the renderer until there is a volume
        loaded and ready to be viewed. Otherwise, the rendering pipeline
        will throw an exception.
        """

        if (self.v_mapper.GetTotalNumberOfInputConnections() > 0
                and self.renderer.GetVolumes().GetNumberOfItems() == 0):
            self.renderer.AddVolume(self.volume)
            logger.debug("Added volume to renderer.")

    def vtk_render(self) -> None:
        """Request a render from the UI thread.

        This method can be safely called from any thread.
        """

        # noinspection PyUnresolvedReferences
        self._render_signal.emit()

    @pyqtSlot()
    def _vtk_render_slot(self) -> None:
        """Force VTK to render the volume immediately.

        Catch the _render_signal emitted from the rendering thread and
        perform the rendering in the UI thread. The arguments passed by the
        emitter are irrelevant. Rendering will not be attempted when the
        volume mapper hasn't been set up.
        """

        if self.renderer.GetVolumes().GetNumberOfItems() > 0:
            self.interactor.GetRenderWindow().Render()
            logger.info("VTK rendered.")

    def add_actor(self, actor: vtkActor) -> None:
        """Request that the UI thread add the passed actor."""

        # noinspection PyUnresolvedReferences
        self._add_actor_signal.emit(actor)

    @pyqtSlot(vtkActor)
    def _add_actor_slot(self, actor: vtkActor) -> None:
        """Add the actor on the UI thread.

        An OpenGL error may occur if actors are added outside the thread
        with the OpenGL context.
        """

        self.renderer.AddActor(actor)
        logger.info("Actor added.")

    def remove_actor(self, actor: vtkActor) -> None:
        """Request that the UI thread remove the passed actor."""

        # noinspection PyUnresolvedReferences
        self._remove_actor_signal.emit(actor)

    @pyqtSlot(vtkActor)
    def _remove_actor_slot(self, actor: vtkActor) -> None:
        """Remove the actor on the UI thread.

        An OpenGL error may occur if actors are added outside the thread
        with the OpenGL context.
        """

        self.renderer.RemoveActor(actor)
        logger.info("Actor removed.")

    def save_png(self, file_path: str, compression_level: int = 5) -> None:
        """Save the current rendered view to an PNG image at the path specified.

        The compression level can range from 0 (none) to 9 (highest).
        """

        image_writer = vtkPNGWriter()
        image_writer.SetCompressionLevel(compression_level)
        self._save_image(file_path, image_writer)

    def save_jpeg(self, file_path: str, quality: int = 93) -> None:
        """Save the current rendered view to an JPEG image at the path specified.

        The quality can range from 0 (lowest) to 100 (highest).
        """

        image_writer = vtkJPEGWriter()
        image_writer.SetQuality(quality)
        self._save_image(file_path, image_writer)

    def save_tiff(self, file_path: str) -> None:
        """Save the current rendered view to an TIFF image at the path specified.

        The default compression algorithm is "deflate", for simplicity.
        """

        image_writer = vtkTIFFWriter()
        image_writer.SetCompressionToDeflate()
        self._save_image(file_path, image_writer)

    def _save_image(self, file_path: str, image_writer: vtkImageWriter) -> None:
        """Save the current rendered view to an image at the path specified."""

        w2if = vtkWindowToImageFilter()
        w2if.SetInput(self.interactor.GetRenderWindow())
        image_writer.SetInputConnection(w2if.GetOutputPort())
        image_writer.SetFileName(file_path)
        image_writer.Write()
