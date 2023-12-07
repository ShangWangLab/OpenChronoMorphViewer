"""Main function file for the 4D viewer application.

This was originally developed to load large 3D volumes captured using an
OCT microscope and manage them in memory to play volumetric video with
Doppler as quickly as possible.

Developed for Python version 3.11.4

Required 3rd party packages:
* NumPy 1.25.2 - for 3D data operations
* psutil 5.9.5 - for getting the current RAM usage
* PyNRRD 1.0.0 (Nearly Raw Raster Data) - for the image file format
* PyQt5 5.15.2.2.3 - for the user interface
* SciPy 1.11.1 - for the "cdist" function
* PyVTK 9.2.6 - for volumetric rendering
"""

import logging

from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from logmanager import LogManager

logger = logging.getLogger(__name__)


def compile_ui() -> None:
    """Compile Qt's UI files to make importable user interfaces in Python."""

    packages = [
        "main_window",
        "settings_camera",
        "settings_channel",
        "settings_clipping_spline",
        "settings_orientation_marker",
        "settings_plane",
        "settings_scale_bar",
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

    try:
        # Handle high resolution displays.
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
        compile_ui()

        # We need to import this *after* compiling the UI files or the imports
        # will not be up-to-date.
        from mainwindow import MainWindow

        app = QApplication([])
        main_window = MainWindow()
        main_window.show()
        main_window.start()
        app.exec()
        logger.info("Application exited correctly.")
    except RuntimeError as e:
        logger.exception(f"UI thread crashed: {e}")
    log_manager.end()


if __name__ == "__main__":
    main()
