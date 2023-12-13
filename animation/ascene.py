import copy
import json


class AScene:
    """Animation scenes are used to initialize regular scenes.

    They have a simple hierarchical data structure similar to that of a JSON file.
    """

    def __init__(self, struct: list[dict]) -> None:
        self.items = {}
        self.clipping_planes = []
        self.control_points = []
        self.image_channels = []

        for item in struct:
            t = item["type"]
            if t == "ClippingPlane":
                self.clipping_planes.append(item)
            elif t == "ControlPoint":
                self.control_points.append(item)
            elif t == "ImageChannel":
                self.image_channels.append(item)
            else:
                self.items[t] = item

    def copy(self) -> "AScene":
        """Copy the underlying data structure to a new animation scene."""

        return AScene(copy.deepcopy(self.to_struct()))

    def to_struct(self) -> list[dict]:
        """Return a JSON object which may be converted to an animation scene."""

        struct = []
        struct.extend(self.items.values())
        struct.extend(self.image_channels)
        struct.extend(self.control_points)
        struct.extend(self.clipping_planes)
        return struct

    @staticmethod
    def load(file_path: str) -> "AScene":
        """Read the scene file at the path specified and produce an animation scene."""

        with open(file_path, "r") as file:
            scene_struct: list[dict] = json.load(file)

        return AScene(scene_struct)
