import logging
from typing import Optional

from vtkmodules.vtkIOImage import vtkPNGWriter
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import (
    vtkRenderWindow,
    vtkRenderWindowInteractor,
    vtkRenderer,
    vtkVolume,
    vtkVolumeProperty,
    vtkWindowToImageFilter,
)
from vtkmodules.vtkRenderingVolumeOpenGL2 import vtkOpenGLGPUVolumeRayCastMapper

from volumeimage import VolumeImage

logger = logging.getLogger(__name__)


class AView:
    """Manages rendering of the 3D volume using the VTK library.

    Contains the vtkRenderer, volume mapper, volume properties, and
    interactor. Basically, most of the core VTK objects. Uses
    multithreading to coordinate rendering operations.
    """

    def __init__(self, win_size: tuple[int, int], magnification: int = 1, show: bool = False) -> None:
        self.win_size: tuple[int, int] = win_size
        self.magnification: int = magnification

        self.ren_win: vtkRenderWindow = vtkRenderWindow()
        self.ren_win.SetSize(*win_size)
        self.ren_win.SetWindowName("OCMV Animation Renderer")
        self.ren_win.SetShowWindow(show)

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
        self.ren_win.AddRenderer(self.renderer)

        logger.debug("Setting up the interactor...")
        self.interactor = vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.ren_win)
        self.interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self.interactor.Initialize()
        logger.debug("Set up the interactor!")

        self.last_volume: Optional[VolumeImage] = None

    def close(self) -> None:
        """Clean up the render window so it is safe to delete."""

        self.ren_win.Finalize()
        self.interactor.TerminateApp()

    def set_volume_input(self, volume: VolumeImage) -> None:
        """Sets the VolumeImage given as the volume mapper's input."""

        if self.last_volume is not None and self.last_volume != volume:
            self.last_volume.unload()
        self.last_volume = volume

        self.v_mapper.SetInputConnection(
            volume.get_vtk_image().GetOutputPort()
        )
        logger.debug("Added volume data to mapper.")

        if (self.v_mapper.GetTotalNumberOfInputConnections() > 0
                and self.renderer.GetVolumes().GetNumberOfItems() == 0):
            self.renderer.AddVolume(self.volume)
            logger.debug("Added volume to renderer.")

    def vtk_render(self) -> None:
        """Request a render from the UI thread.

        This method can be safely called from any thread.
        """

        if self.renderer.GetVolumes().GetNumberOfItems() > 0:
            self.ren_win.Render()

    def to_image(self, file_path: str) -> None:
        """Save the current rendered frame to an image at the path specified."""

        w2if = vtkWindowToImageFilter()
        w2if.SetInput(self.ren_win)
        #w2if.SetScale(self.magnification)
        image_writer = vtkPNGWriter()
        image_writer.SetInputConnection(w2if.GetOutputPort())
        image_writer.SetFileName(file_path)
        image_writer.Write()

        assert self.ren_win.GetSize() == self.win_size, (
            "The render window has changed size unexpectedly! "
            "Do you have a large enough monitor for the video you are rendering?")
