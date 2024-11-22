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

"""Utilities for when this program has been bundled as a stand-alone application via PyInstaller"""

import sys


IS_BUNDLED: bool = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
# It would be nice to do this, but the paths are hardcoded in the UI files:
# GFX_DIR: str = "_internal/gfx" if IS_BUNDLED else "ui/graphics"
GFX_DIR: str = "ui/graphics"
