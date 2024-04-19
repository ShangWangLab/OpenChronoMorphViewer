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

    def __add__(self, other: "AScene") -> "AScene":
        """Combine this scene with the other scene.

        Items in the scene on the right of the addition sign will be prioritized
        over items in the left scene. E.g., when both scenes contain a camera,
        the right scene's camera will dominate.

        Nonetheless, you should avoid adding scenes which contain overlapping
        items.
        """

        result = AScene([])
        result.items = self.items | other.items
        result.clipping_planes = self.clipping_planes + other.clipping_planes
        result.control_points = self.control_points + other.control_points
        result.image_channels = self.image_channels + other.image_channels
        return result.copy()

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
