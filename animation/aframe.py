import copy
from typing import Optional

from animation.amainscene import AMainScene
from animation.annotation import Annotation
from animation.ascene import AScene
from animation.aview import AView
from volumeimage import VolumeImage


class AFrame:
    """An animation frame with a volume and scene settings to render it with."""

    def __init__(self, volume: VolumeImage) -> None:
        self.volume: VolumeImage = volume
        self.scene: Optional[AScene] = None
        self.annotations: list[Annotation] = []

    def apply_scene(self, scene: AScene) -> None:
        """Set this animation frame's scene to a copy of the one passed."""

        self.scene = scene.copy()

    def copy(self) -> "AFrame":
        """Make a new, identical animation frame."""

        a_frame = AFrame(self.volume)
        if self.scene is not None:
            a_frame.apply_scene(self.scene)
        a_frame.annotations = copy.copy(self.annotations)
        return a_frame

    def render(self, view: AView, scene: AMainScene, path_out: str) -> None:
        """Create an image file corresponding to this animation frame.

        :param view: The global rendering object.
        :param scene: The global scene on which to apply this frame's scene.
        :param path_out: The file path for the image output.
        """

        # Just load; unloading volumes is handled by the AView.
        self.volume.load()
        view.set_volume_input(self.volume)
        scene.volume_update(self.volume)

        if self.scene is not None:
            errors = scene.from_struct(self.scene.to_struct())
            assert len(errors) == 0, "Errors occurred while loading the scene:\n" + "\n".join(errors)

        for annotation in self.annotations:
            annotation.attach(view.renderer)

        view.to_image(path_out)

        for annotation in self.annotations:
            annotation.detach(view.renderer)

        # Optional, but it makes the window unfreeze.
        view.interactor.ProcessEvents()
