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
import os
from typing import Optional
import webbrowser

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
)

from main.cachelimiter import CacheLimiter
from main.dialogrendersettings import DialogRenderSettings
from main.errorreporter import ErrorReporter
from main.scene import Scene
from main.timeline import Timeline
from main.timelineslider import TimelineSlider
from main.viewframe import ViewFrame
from main.volumeupdater import VolumeUpdater
from ui.main_window import Ui_MainWindow

logger = logging.getLogger(__name__)


OCMV_VERSION: str = "0.9"
PROJECT_URL: str = "https://github.com/ShangWangLab/OpenChronoMorphViewer"
ACKNOWLEDGEMENTS: str = """\
Funded by the National Institutes of Health (R35GM142953).

A special thanks to our colleagues at Dr. Shang Wang's Biophotonics Lab! \
https://www.shangwanglab.org/team"""


def on_go_to_project_page(_: bool = False) -> None:
    """Respond to the action to navigate a web browser to the project page."""

    webbrowser.open(PROJECT_URL)


class MainWindow(QMainWindow):
    """A Qt window that handles events and acts as the root data structure.

    This class is in charge of all events and everything UI-related except
    for the VTK rendering frame, which is stored under ViewFrame.
    """

    def __init__(self) -> None:
        super().__init__()

        self.dialog_render_settings: Optional[DialogRenderSettings] = None
        # Current Working Directory to use with file selectors.
        self.CWD_path: str = ""

        # Qt interface setup.
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self._create_view_frame()
        self.error_reporter: ErrorReporter = ErrorReporter(self)
        self.timeline = Timeline(self.error_reporter)
        self.cache_limiter: CacheLimiter = CacheLimiter(self.ui, self.timeline)
        self.cache_limiter.init_cache_limit()
        self.scene = Scene(
            self.error_reporter,
            self.ui,
            self.view_frame,
            self.timeline
        )
        self.scene.initialize_scene_list()
        self.volume_updater = VolumeUpdater(
            self.view_frame,
            self.timeline,
            self.scene
        )
        self.timeline_slider = TimelineSlider(
            self.ui,
            self.volume_updater,
            self.timeline
        )
        self._bind_event_listeners()
        self.timeline.set_priority_threaders([
            self.timeline_slider.auto_player,
            self.volume_updater
        ])
        self.timeline.start_caching()

    def _create_view_frame(self) -> None:
        """Initialize the ViewFrame to replace the layout_vtk widget."""

        self.view_frame = ViewFrame(self.ui.frame_vtk)
        self.ui.layout_vtk = QHBoxLayout()  # type: ignore
        self.ui.layout_vtk.addWidget(self.view_frame)  # type: ignore
        self.ui.layout_vtk.setContentsMargins(0, 0, 0, 0)  # type: ignore
        self.ui.frame_vtk.setLayout(self.ui.layout_vtk)  # type: ignore

    def _bind_event_listeners(self) -> None:
        """Attach all the UI elements to their respective functions."""

        self.ui.action_open.triggered.connect(self.on_file_open)
        self.ui.action_open.setShortcut("Ctrl+O")

        self.ui.action_save_scene.triggered.connect(self.on_save_scene)
        self.ui.action_save_scene.setShortcut("Ctrl+S")
        self.ui.action_save_scene_as.triggered.connect(self.on_save_scene_as)
        self.ui.action_save_scene_as.setShortcut("Ctrl+Shift+S")
        self.ui.action_save_keyframe.triggered.connect(self.on_save_keyframe)
        self.ui.action_save_keyframe.setShortcut("Ctrl+K")
        self.ui.action_load_scene.triggered.connect(self.on_load_scene)
        self.ui.action_load_scene.setShortcut("Ctrl+Shift+O")

        self.ui.action_screenshot.triggered.connect(self.on_screenshot)
        self.ui.action_screenshot.setShortcut("Ctrl+R")
        self.ui.action_render_settings.triggered.connect(self.on_show_render_settings)

        self.ui.action_acknowledgements.triggered.connect(self.on_show_acknowledgements)
        self.ui.action_project.triggered.connect(on_go_to_project_page)
        self.ui.action_version.triggered.connect(self.on_show_version)

        # This is an example of how to add a keybinding to the main window.
        # However, I prefer to bind these to actions in the menu bar as a
        # form of documentation for the function:
        # self.shortcut_xxx = QShortcut("Ctrl+x", self)
        # self.shortcut_xxx.activated.connect(self.on_xxx)

        self.cache_limiter.bind_event_listeners()
        self.timeline_slider.bind_event_listeners()
        self.scene.bind_event_listeners()

    def on_file_open(self, _: bool = False) -> None:
        """Respond to the "File->Open Volumes..." action.

        Opens a dialog for the user to select volume files to be added to
        the timeline.
        """

        file_paths, file_filter = QFileDialog.getOpenFileNames(
            self,                                                    # Parent.
            "Select one or more volumes to load",                    # Caption.
            self.CWD_path,                                           # Current working directory.
            "Nearly Raw Raster Data (*.nrrd *.nhdr);;Any file (*)")  # File filter options.
        if not file_paths:
            return

        # Update the current directory in case they open another file.
        self.CWD_path = os.path.split(file_paths[0])[0]

        # This might take a while to touch all the file headers.
        progress_bar = QProgressDialog(
            "Checking volume headers...",  # Label.
            "Cancel",                      # Cancel button text.
            0,                             # Minimum progress value.
            len(file_paths),               # Maximum progress value.
            self)  # Parent.
        progress_bar.setWindowModality(Qt.WindowModal)  # type: ignore
        progress_bar.setWindowTitle("Checking files")
        # Show the dialog if loading takes longer than x ms. The default is
        # 4000, which is usually too long.
        progress_bar.setMinimumDuration(1000)

        def on_update(progress: int) -> bool:
            progress_bar.setValue(progress)
            return progress_bar.wasCanceled()

        file_errors = self.timeline.set_file_paths(file_paths, on_update)
        if self.timeline.available:
            self.timeline_slider.reset()
            self.scene.on_timeline_loaded(self.timeline)
            self.volume_updater.queue()
        if len(file_errors) > 0:
            self.error_reporter.file_errors(file_errors)

    def on_save_scene(self, _: bool = False) -> None:
        """Responds to "Save Scene..." action.

        Only opens a file dialog if no save file has been previously created.
        """

        if self.scene.last_save_path:
            self.scene.save_to_file()
        else:
            self.on_save_scene_as()

    def on_save_scene_as(self, _: bool = False) -> None:
        """Responds to "Save Scene As..." action.

        Always open a file dialog.
        """

        default_path = self.scene.last_save_path or self.CWD_path
        file_path, file_filter = QFileDialog.getSaveFileName(
            self,                                 # Parent.
            "Save scene",                         # Caption.
            default_path,                         # Directory.
            "Scene File (*.json);;Any File (*)")  # File filter options.
        if not file_path:
            return
        self.scene.save_to_file(file_path)

    def on_save_keyframe(self, _: bool = False) -> None:
        """Responds to "Save Keyframe..." action."""

        default_path = self.scene.default_keyframe_path(self.CWD_path)
        file_path, file_filter = QFileDialog.getSaveFileName(
            self,                                    # Parent.
            "Save keyframe",                         # Caption.
            default_path,                            # File/directory.
            "Keyframe File (*.json);;Any file (*)")  # File filter options.
        if not file_path:
            return
        self.scene.save_to_file(file_path, keyframe=True)

    def on_load_scene(self, _: bool = False) -> None:
        """Responds to "Load Scene..." action."""

        default_dir = (
            os.path.split(self.scene.last_save_path)[0]
            if self.scene.last_save_path
            else self.CWD_path
        )
        file_path, file_filter = QFileDialog.getOpenFileName(
            self,                                 # Parent.
            "Load scene",                         # Caption.
            default_dir,                          # Directory.
            "Scene File (*.json);;Any file (*)")  # File filter options.
        if not file_path:
            return
        self.scene.load_from_file(file_path)

    def on_screenshot(self, _: bool = False) -> None:
        """Respond to action to save the current view as an image file."""

        file_path, file_filter = QFileDialog.getSaveFileName(
            self,  # Parent.
            "Save image",  # Caption.
            self.CWD_path,  # Directory.
            "PNG image (*.png);;TIFF image (*.tif *.tiff);;JPEG image (*.jpg *.jpeg)")  # File filter options.
        if not file_path:
            return
        # Update the current directory in case they save another file.
        self.CWD_path = os.path.split(file_path)[0]

        logger.debug(f"Chosen file filter: {file_filter}")
        # Check which sort of image they are trying to save as, as make an appropriate image writer.
        if file_filter == "JPEG image (*.jpg)":
            self.view_frame.save_jpeg(file_path)
        elif file_filter == "TIFF image (*.tiff)":
            self.view_frame.save_tiff(file_path)
        elif file_filter == "PNG image (*.png)":
            self.view_frame.save_png(file_path)
        else:
            logger.warning("Unrecognized file filter. Defaulting to PNG.")
            self.view_frame.save_png(file_path)

    def on_show_render_settings(self, _: bool = False) -> None:
        """Respond to the action to show the render settings dialog."""

        self.dialog_render_settings = DialogRenderSettings(self, self.view_frame)
        self.dialog_render_settings.open()

    def on_show_acknowledgements(self, _: bool = False) -> None:
        """Respond to the action to show the acknowledgements."""

        QMessageBox.information(self, 'Acknowledgements', ACKNOWLEDGEMENTS)

    def on_show_version(self, _: bool = False) -> None:
        """Respond to the action to display the current version number."""

        QMessageBox.information(
            self, 'Version', f'OCMV version {OCMV_VERSION}')

    def start(self) -> None:
        """Pass the 'start' signal to objects that need it."""

        self.view_frame.start()
