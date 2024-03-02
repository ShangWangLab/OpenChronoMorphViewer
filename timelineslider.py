import logging
from typing import Any, Optional

from autoplayer import AutoPlayer
from eventfilter import EditDoneEventFilter
from timeline import Timeline
from ui.main_window import Ui_MainWindow
from validatenumericinput import (
    validate_float,
    validate_int,
)
from volumeupdater import VolumeUpdater

logger = logging.getLogger(__name__)


class TimelineSlider:
    """Manages the UI related to the timeline slider and associated buttons."""

    def __init__(self,
                 ui: Ui_MainWindow,
                 volume_updater: VolumeUpdater,
                 timeline: Timeline) -> None:
        self.ui = ui
        self.volume_updater = volume_updater
        self.timeline = timeline
        self.auto_player = AutoPlayer(self, volume_updater, fps=30.)
        self.edit_fps_filter: Optional[EditDoneEventFilter] = None
        self.edit_cycles_filter: Optional[EditDoneEventFilter] = None
        self.n_cycles: int = 1
        self.cycles_remaining: int = self.n_cycles
        self.reset()

    def reset(self) -> None:
        """Return everything to its default state."""

        self.cycles_remaining = self.n_cycles
        self.auto_player.set_playing(False)
        self.ui.button_play.setChecked(False)
        self.ui.edit_goto_time.setText("1")
        self.ui.slider_timeline.setMinimum(0)
        # The timeline might be empty when this is first called.
        self.ui.slider_timeline.setMaximum(max(0, len(self.timeline) - 1))
        self.ui.slider_timeline.setSingleStep(1)
        self.ui.slider_timeline.setValue(0)
        self.ui.slider_timeline.setStyleSheet(self._get_style_sheet())
        self._update_fps_field()
        self._update_cycles_field()
        self._update_label()

    def _get_style_sheet(self) -> str:
        """Make the slider style sheet to highlight different groups in alternating tones.

        An alternating style sheet is only produced when there are at least two
        volumes in the timeline which share a group. Otherwise, the empty style
        sheet is returned.

        "Singletons", i.e., volumes which are the only examples of their group
        index, are consolidated with their neighbors to form blocks. This
        prevents lots of alternating colors when unrelated volumes are loaded.
        """

        s_lens = self.timeline.get_group_lengths()
        s_lens = _consolidate_ones(s_lens)
        if len(s_lens) < 2:
            return ""  # The default style sheet.

        n = sum(s_lens)

        # This is the gap on the left and right of the slider. This value is a
        # hack that works well enough for typical window sizes.
        edge_width = 0.005
        gap_width = (1 - 2 * edge_width) / (n - 1)

        # Normalized gradient stop indices range from [0-1].
        stops: list[float] = [0.]
        stop: float = edge_width - gap_width/2
        epsilon = 1e-5  # The width of the transitions is small but non-zero.
        for sl in s_lens[:-1]:
            stop += sl * gap_width
            stops.append(stop)
            stops.append(stop + epsilon)
        stops.append(1.)

        style_sheet = ["QSlider {background: qlineargradient(x1: 0, x2: 1"]
        for i, s in enumerate(stops):
            # Light and dark grey alternate (color code #eee = 0xe0e0e0, etc.).
            color = "eee" if i // 2 % 2 == 0 else "ccc"
            style_sheet.append(f", stop:{s:.6g} #{color}")
        style_sheet.append(");}")
        return "".join(style_sheet)

    def _update_fps_field(self) -> None:
        """Set the volume playback rate in the UI."""

        self.ui.edit_fps.setText(f"{self.auto_player.fps:0.2f}")

    def _read_fps_field(self) -> None:
        """Interpret and validate the volume playback rate in the UI."""

        fps = validate_float(self.ui.edit_fps.text(), 0., 99.99)
        self.auto_player.fps = fps
        self._update_fps_field()

    def _update_cycles_field(self) -> None:
        """Set the number of cycles to repeat in the UI."""

        self.ui.edit_n_cycles.setText(str(self.n_cycles))

    def _read_cycles_field(self) -> None:
        """Interpret and validate the number of cycles to repeat in the UI."""

        # This is intentionally set up so that n_cycles = 0 causes it to loop forever.
        # It's a feature, not a bug.
        self.n_cycles = validate_int(self.ui.edit_n_cycles.text(), 0, 999)
        self.cycles_remaining = self.n_cycles
        self._update_cycles_field()

    def _update_label(self) -> None:
        """Set the timeline info label.

        It is safe to call this function even when no volumes are available
        from which to get the label.
        """

        self.ui.label_timepoint.setText(
            self.timeline.get_label() if self.timeline else ""
        )

    def bind_event_listeners(self) -> None:
        """Set UI input functions for the timeline slider and controls."""

        self.ui.button_play.clicked.connect(self.auto_player.set_playing)
        # If you listen for sliderMoved instead of valueChanged, the event
        # will trigger during a move, not just on a slider drop. That will
        # request volumes to load unnecessarily.
        self.ui.slider_timeline.valueChanged.connect(self.set_index)
        self.ui.edit_goto_time.returnPressed.connect(self._on_goto)
        self.ui.button_goto_time.clicked.connect(self._on_goto)
        self.ui.button_prev.clicked.connect(self._on_prev_group)
        self.ui.button_next.clicked.connect(self._on_next_group)

        # We need to keep this variable around or the garbage collector will
        # collect it.
        self.edit_fps_filter = EditDoneEventFilter(self._read_fps_field)
        self.ui.edit_fps.installEventFilter(self.edit_fps_filter)
        self.edit_cycles_filter = EditDoneEventFilter(self._read_cycles_field)
        self.ui.edit_n_cycles.installEventFilter(self.edit_cycles_filter)

        # Shortcuts.
        self.ui.action_play_pause.triggered.connect(self.ui.button_play.click)
        self.ui.action_play_pause.setShortcut("space")
        self.ui.action_next_volume.triggered.connect(lambda _: self.add(1))
        self.ui.action_next_volume.setShortcut("right")
        self.ui.action_prev_volume.triggered.connect(lambda _: self.add(-1))
        self.ui.action_prev_volume.setShortcut("left")
        self.ui.action_next_sequence.triggered.connect(self._on_next_group)
        self.ui.action_next_sequence.setShortcut("page down")
        self.ui.action_prev_sequence.triggered.connect(self._on_prev_group)
        self.ui.action_prev_sequence.setShortcut("page up")

        self.ui.action_start_of_sequence.triggered.connect(self._goto_group_start)
        self.ui.action_start_of_sequence.setShortcut(",")
        self.ui.action_end_of_sequence.triggered.connect(self._goto_group_end)
        self.ui.action_end_of_sequence.setShortcut(".")

    def set_index(self, index: int) -> None:
        """Update the slider position (0-based indexing).

        Ensures that the timeline and volume view stay up to date, too. It
        is safe to call this function even when there is nothing in the
        timeline.
        """

        if not self.timeline:
            return

        logger.info(f"Set_index({index}).")
        # Can't call self.ui.slider_timeline.setValue(index) or it will
        # trigger an event that will call this function again.
        self.ui.slider_timeline.setSliderPosition(index)
        self.timeline.seek(index)
        self._update_label()
        self.volume_updater.queue()

    def add(self, delta: int) -> None:
        """Add delta to the slider index with wrap-around.

        It is safe to call this function even when there is nothing in the
        timeline.
        """

        if not self.timeline:
            return

        slider_n = 1 + self.ui.slider_timeline.maximum()
        p = self.ui.slider_timeline.sliderPosition()
        p_next = (p + delta) % slider_n

        i0: int = self.timeline.get_first_group_index()
        i1: int = self.timeline.get_last_group_index()
        logger.debug(
            f"Add {delta} to {p}. Bounds: {i0} to {i1}. Cycles: {self.cycles_remaining}/{self.n_cycles}")

        crossing_left_bound: bool = delta == -1 and p == i0
        crossing_right_bound: bool = delta == +1 and p == i1
        crossing: bool = crossing_left_bound or crossing_right_bound

        if crossing and i0 != i1:
            if self.cycles_remaining == 1:
                self.cycles_remaining = self.n_cycles
                # Continue as usual.
            else:
                self.cycles_remaining -= 1
                p_next = i1 if crossing_left_bound else i0

        # We only bother to define cycle wrapping for the case of a single step forward or backward.
        # If cycles_remaining == 0, this will never stop. This is a feature, not a bug.

        logger.debug(f"Result: {p_next}. Cycles: {self.cycles_remaining}/{self.n_cycles}")
        self.set_index(p_next)

    def _on_goto(self, _: Any = None) -> None:
        """Respond to the "go to" button event."""

        if not self.timeline:
            return

        # UI indices start at 1, not 0.
        index = validate_int(self.ui.edit_goto_time.text(), 1, len(self.timeline))
        self.ui.edit_goto_time.setText(str(index))
        self.set_index(index - 1)
        self.cycles_remaining = self.n_cycles

    def _on_prev_group(self, _: Any = None) -> None:
        """Respond to the "previous group" button event."""

        if not self.timeline:
            return

        self.set_index(self.timeline.get_prev_group_index())
        self.cycles_remaining = self.n_cycles

    def _on_next_group(self, _: Any = None) -> None:
        """Respond to the "next group" button event."""

        if not self.timeline:
            return

        self.set_index(self.timeline.get_next_group_index())
        self.cycles_remaining = self.n_cycles

    def _goto_group_start(self, _: Any = None) -> None:
        """Respond to a key event, jumping to the beginning of the current group."""

        if not self.timeline:
            return

        self.set_index(self.timeline.get_first_group_index())
        self.cycles_remaining = self.n_cycles

    def _goto_group_end(self, _: Any = None) -> None:
        """Respond to a key event, jumping to the end of the current group."""

        if not self.timeline:
            return

        self.set_index(self.timeline.get_last_group_index())
        self.cycles_remaining = self.n_cycles


def _consolidate_ones(arr: list[int]) -> list[int]:
    """Consolidate any adjacent 1's into their sums.

    Example:
        consolidate_ones([70, 70, 1, 73, 1, 1, 1, 75, 1, 1])
        -> [70, 70, 1, 73, 3, 75, 2]
    """

    result: list[int] = []
    ones_sum: int = 0

    for num in arr:
        if num == 1:
            ones_sum += 1
        else:
            if ones_sum > 0:
                result.append(ones_sum)
                ones_sum = 0
            result.append(num)

    if ones_sum > 0:
        result.append(ones_sum)

    return result
