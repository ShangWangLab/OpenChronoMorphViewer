import logging
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QProgressDialog,
    QShortcut,
)

from cachelimiter import CacheLimiter
from errorreporter import ErrorReporter
from scene import Scene
from timeline import Timeline
from timelineslider import TimelineSlider
from ui.main_window import Ui_MainWindow
from viewframe import ViewFrame
from volumeupdater import VolumeUpdater

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """A Qt window that handles events and acts as the root data structure.

    This class is in charge of all events and everything UI-related except
    for the VTK rendering frame, which is stored under ViewFrame.
    """

    def __init__(self) -> None:
        super().__init__()

        # Current Working Directory to use with file selectors.
        self.CWD_path: str = "."

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

        # TODO: Implement
        # self.ui.action_increase_phase.triggered.connect(self.)
        self.ui.action_increase_phase.setShortcut("Ctrl+Up")
        # self.ui.action_decrease_phase.triggered.connect(self.)
        self.ui.action_decrease_phase.setShortcut("Ctrl+Down")

        # This is an example of how to add a keybinding to the main window,
        # but I generally prefer to bind these to actions in the menu bar as a
        # form of functionality documentation.
        # self.shortcut_file_open = QShortcut("Ctrl+O", self)
        # self.shortcut_file_open.activated.connect(self.on_file_open)

        # TODO: delete this shortcut
        self.shortcut_debug = QShortcut("t", self)
        # noinspection PyUnresolvedReferences
        self.shortcut_debug.activated.connect(self.debug)

        self.cache_limiter.bind_event_listeners()
        self.timeline_slider.bind_event_listeners()
        self.scene.bind_event_listeners()

    def debug(self, _: bool = False) -> None:
        """TODO: remove this debugging code."""

    def on_file_open(self, _: bool = False) -> None:
        """Respond to the "File->Open Volumes..." action.

        Opens a dialog for the user to select volume files to be added to
        the timeline.
        """

        file_paths, file_filter = QFileDialog.getOpenFileNames(
            self,                                                    # Parent.
            "Select one or more volumes to load",                    # Caption.
            self.CWD_path,                                           # Current working directory.
            "Nearly Raw Raster Data (*.nrrd;*.nhdr);;Any File (*)")  # File filter options.

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

        if self.scene.last_save_path is None:
            self.on_save_scene_as()
        else:
            self.scene.save_to_file(self.scene.last_save_path)

    def on_save_scene_as(self, _: bool = False) -> None:
        """Responds to "Save Scene As..." action.

        Always open a file dialog.
        """

        file_path, file_filter = QFileDialog.getSaveFileName(
            self,                                 # Parent.
            "Save scene",                         # Caption.
            self.CWD_path,                        # Directory.
            "Scene File (*.json);;Any File (*)")  # File filter options.
        if not file_path:
            return
        # Update the current directory in case they open another file.
        self.CWD_path = os.path.split(file_path)[0]
        self.scene.last_save_path = file_path
        self.scene.save_to_file(file_path)
        self.scene.keyframe_count = 0

    def on_save_keyframe(self, _: bool = False) -> None:
        """Responds to "Save Keyframe..." action."""

        if self.scene.last_save_path is None:
            file_path, file_filter = QFileDialog.getSaveFileName(
                self,                                    # Parent.
                "Save keyframe",                         # Caption.
                self.CWD_path,                           # Directory.
                "Keyframe File (*.json);;Any File (*)")  # File filter options.
            if not file_path:
                return
            # Update the current directory in case they open another file.
            self.CWD_path = os.path.split(file_path)[0]
            self.scene.last_save_path = file_path
            self.scene.keyframe_count = 0
        else:
            file_path = self.scene.last_save_path
        self.scene.save_to_file(file_path, keyframe=True)
        self.scene.keyframe_count += 1

    def on_load_scene(self, _: bool = False) -> None:
        """Responds to "Load Scene..." action."""

        file_path, file_filter = QFileDialog.getOpenFileName(
            self,                                 # Parent.
            "Load scene",                         # Caption.
            self.CWD_path,                        # Directory.
            "Scene File (*.json);;Any File (*)")  # File filter options.
        if not file_path:
            return
        # Update the current directory in case they open another file.
        self.CWD_path = os.path.split(file_path)[0]
        self.scene.last_save_path = file_path
        self.scene.load_from_file(file_path)

    def on_screenshot(self, _: bool = False) -> None:
        """Respond to action to save the current view as an image file."""

        file_path, file_filter = QFileDialog.getSaveFileName(
            self,  # Parent.
            "Save image",  # Caption.
            self.CWD_path,  # Directory.
            "PNG image (*.png);;TIFF image (*.tiff);;JPEG image (*.jpg)")  # File filter options.
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

    def start(self) -> None:
        """Pass the 'start' signal to objects that need it."""

        self.view_frame.start()