import logging
from threading import (
    Lock,
    Thread,
)
from typing import Optional

from scene import Scene
from timeline import Timeline
from viewframe import ViewFrame

logger = logging.getLogger(__name__)


class VolumeUpdater:
    """Updates the visible volume.

    Provides options to asynchronously update the currently viewed volume
    through a ViewFrame and Timeline by operating a separate thread.
    """

    def __init__(self,
                 view_frame: ViewFrame,
                 timeline: Timeline,
                 scene: Scene) -> None:
        # Keep handles used for updating the current volume.
        self.view_frame = view_frame
        self.timeline = timeline
        self.scene = scene

        # This is the thread that performs a volume update. When it
        # finishes, it is destroyed and a new thread is eventually created.
        self.thread: Optional[Thread] = None
        # This lock prevents race conditions related to both multiple
        # threads starting up and the must_update flag from being set
        # when there is no living thread to carry out the request indicated.
        self.load_lock = Lock()
        self.must_update: bool = False
        logger.debug("Initialized.")

    def queue(self) -> None:
        """Indicates that a new update is needed and returns immediately.

        When a volume update is requested while the previous update has yet
        to complete, this function indicates that a new update is needed and
        returns immediately to avoid bogging down the main loop with volume
        loading operations.

        This is the only function that is allowed to start the volume
        updater thread. The volume updater thread can also recursively run
        itself if still needed, as indicated by the must_update flag.
        """

        # Use a lock so multiple queue requests don't race to create the
        # update thread.
        with self.load_lock:
            self.must_update = True

            if not (self.thread and self.thread.is_alive()):
                logger.info("New thread.")
                # There is no thread, so start one.
                self.thread = Thread(
                    target=self._run_thread,
                    daemon=True
                )
                self.thread.start()
            else:
                logger.info("Set the flag and returned.")

    def _run_thread(self) -> None:
        """The loop for the volume update thread.

        This method will hold load_lock for as little time as possible since
        this lock has the potential to freeze the UI thread. It should only
        be held while checking and setting the must_update flag.
        """

        try:
            self.load_lock.acquire()
            while self.must_update:
                self.must_update = False
                self.load_lock.release()

                # Requesting a rendering should succeed even if there are no
                # volumes available to render. Just do nothing.
                if self.timeline:
                    # This can be a time-consuming operation, during which,
                    # the must_update flag may be changed.
                    logger.info("Getting volume...")
                    # Start the mask thread before getting the volume so
                    # that both can run simultaneously. Store the index just
                    # once to guard against race conditions.
                    index = self.timeline.index
                    volume = self.timeline.get(index, preload=False)
                    mask_thread = self.scene.attach_mask(volume)
                    volume = self.timeline.get(index, preload=True)
                    self.view_frame.set_volume_input(volume)
                    self.scene.volume_update(volume)
                    if mask_thread is not None:
                        logger.info("Waiting for mask to finish...")
                        mask_thread.join()

                self.load_lock.acquire()

            # Verify that the volume has been added to the renderer. Upon
            # startup, this will not be the case. The volume cannot be added
            # until it contains vtkImageData to render, or a non-fatal error
            # will be thrown by the VTK pipeline.
            self.view_frame.attach_volume()

            # Request a rendering from the UI thread. We can't directly call
            # the render function because it would happen outside the UI
            # thread, which is illegal.

            logger.info("Requesting render.")
            self.view_frame.vtk_render()

            # We can't release the load lock before this method returns or else
            # a must_update flag may be raised and never acted upon.
            self.load_lock.release()
        except RuntimeError as e:
            logger.exception(f"Thread error: {e}")

    def wait_for_volume_update(self) -> None:
        """Blocks until the volume update queue is empty."""

        if self.thread is not None:
            self.thread.join()
