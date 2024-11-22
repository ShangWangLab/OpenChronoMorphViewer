#!/usr/bin/python3.11

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

"""Main function file for the Open Chrono-Morph Viewer application.

This was originally developed to load large 3D volumes captured using an
OCT microscope and manage them in memory to play volumetric video with
Doppler as quickly as possible.

Developed for Python version 3.11.4

Required 3rd party packages:
* NumPy 1.25.2 - for 3D data operations
* psutil 5.9.5 - for getting the current RAM usage
* PyNRRD 1.0.0 (Nearly Raw Raster Data) - for the image file format
* PyQt5 5.15.2.2.3 - for the user interface
* PyVTK 9.2.6 - for volumetric rendering
* SciPy 1.11.1 - for the "cdist" function
* tifffile 2023.7.18 - for reading 3D TIFF files

Required 3rd party software:
* FFmpeg 6.1.1 (and added to PATH) - for compiling animation videos

Tested on:
* Window 10 and 11
* macOS 13.0 (experienced issues on 12.6.0)
* Ubuntu 20.04
"""

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from main.bundleutil import IS_BUNDLED
from main.logmanager import LogManager

logger = logging.getLogger(__name__)


def compile_ui() -> None:
    """Compile Qt's UI files to make importable user interfaces in Python."""

    # This will not exist in a bundle, so don't import it at the top level.
    from PyQt5 import uic

    packages = [
        "main_window",
        "settings_camera",
        "settings_channel",
        "settings_clipping_spline",
        "settings_orientation_marker",
        "settings_plane",
        "settings_scale_bar",
        "dialog_render_settings",
    ]

    for name in packages:
        with open(f"ui/{name}.ui") as ui_file:
            with open(f"ui/{name}.py", "w") as py_ui_file:
                uic.compileUi(ui_file, py_ui_file)
        logger.debug(f"Compiled UI for {name}.")


def main() -> None:
    log_manager = LogManager()
    log_manager.start_logging()
    log_manager.start_fault_handler()

    # noinspection PyBroadException
    try:
        # Handle high resolution displays.
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        if IS_BUNDLED:
            logger.info("Running from a bundled application.")
        else:
            logger.info("Running from the installed Python runtime.")
            compile_ui()

        # We need to import this *after* compiling the UI files or the generated
        # Python files will not be up-to-date for following imports.
        from main.mainwindow import MainWindow

        app = QApplication([])
        main_window = MainWindow()
        main_window.show()
        main_window.start()
        app.exec()
        logger.info("Application exited correctly.")
    except:
        logger.exception("UI thread crashed")
    log_manager.end()


if __name__ == "__main__":
    main()
