from typing import Optional

from animation.amainscene import AMainScene
from animation.ascene import AScene
from animation.aview import AView
from volumeimage import VolumeImage


class AFrame:
    """An animation frame with a volume and scene settings to render it with."""

    def __init__(self, volume: VolumeImage) -> None:
        self.volume: VolumeImage = volume
        self.scene: Optional[AScene] = None

    def apply_scene(self, scene: AScene) -> None:
        """TODO"""

        self.scene = scene.copy()

    def copy(self) -> "AFrame":
        """TODO"""

        a_frame = AFrame(self.volume)
        a_frame.apply_scene(self.scene)
        return a_frame

    def render(self, view: AView, scene: AMainScene, path_out: str) -> None:
        """TODO"""

        print("Loading the volume...")
        self.volume.load()
        view.set_volume_input(self.volume)
        scene.volume_update(self.volume)
        print("Loaded the volume!")

        if self.scene is not None:
            if "ClippingSpline" in self.scene.items:
                spline = self.scene.items["ClippingSpline"]
                spline["initialized"] = spline["checked"]
            errors = scene.from_struct(self.scene.to_struct())
            assert len(errors) == 0, \
                "Errors occurred while loading the scene:\n" + "\n".join(errors)

        print(f"Rendering '{path_out}'...")
        view.to_image(path_out)
        # Unloading the volumes is handled by the AView.
        print("Rendered!")

        # Optional, but it makes the window unfreeze.
        view.interactor.ProcessEvents()
