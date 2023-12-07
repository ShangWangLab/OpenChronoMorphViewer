import logging
import time
from threading import Thread
from typing import (
    Optional,
    TYPE_CHECKING,
)

from volumeupdater import VolumeUpdater

logger = logging.getLogger(__name__)

# Issue with circular imports.
if TYPE_CHECKING:
    from timelineslider import TimelineSlider


class AutoPlayer:
    """Automatically increment the timeline slider in the UI.

    Call set_fps to set the maximum playback rate, then call
    set_playing(True) to begin playing.
    """

    def __init__(self,
                 timeline_slider: "TimelineSlider",
                 volume_updater: VolumeUpdater,
                 fps: float = 0.):
        self.timeline_slider = timeline_slider
        self.volume_updater = volume_updater
        self.fps: float = fps
        self.playing = False
        self.thread: Optional[Thread] = None

        logger.debug("Initialized.")

    def set_playing(self, playing: bool) -> None:
        """Sets the "playing" flag and starts the thread if needed."""

        logger.info(f"set_playing({playing})")

        self.playing = playing
        if self.playing and not (self.thread and self.thread.is_alive()):
            logger.info("New thread.")
            self.thread = Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self) -> None:
        """This thread automatically advances the volume display over time."""

        try:
            while self.playing:
                last_update_time = time.time()

                logger.debug("Timeline slider +1...")
                self.timeline_slider.add(1)
                self.volume_updater.wait_for_volume_update()

                update_delta_time = time.time() - last_update_time
                if self.fps <= 0:
                    remaining_time = 1e18
                else:
                    remaining_time = 1 / self.fps - update_delta_time
                while remaining_time > 0 and self.playing:
                    # Maximum of half a second to maintain UI responsiveness.
                    sleep_time = min(0.5, remaining_time)
                    time.sleep(sleep_time)
                    remaining_time -= sleep_time
            logger.info("Thread finished.")
        except RuntimeError as e:
            logger.exception(f"Thread error: {e}")
