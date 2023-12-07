import logging
from threading import (
    Lock,
    Thread,
)
from typing import Optional

from vtkmodules.vtkRenderingCore import vtkActor

from viewframe import ViewFrame
from volumemasktps import VolumeMaskTPS

logger = logging.getLogger(__name__)


class MaskUpdater:
    """Updates the visible mask.

    Provides options to asynchronously update the currently viewed mask
    by operating a separate thread.
    """

    def __init__(self, mask: VolumeMaskTPS, view_frame: ViewFrame) -> None:
        self.mask = mask
        self.view_frame = view_frame

        # This is the thread that performs an update. When it finishes, it
        # is destroyed and a new thread is eventually created.
        self.thread: Optional[Thread] = None
        # This lock prevents race conditions related to both multiple
        # threads starting up, and the must_update flag from being set
        # when there is no living thread to carry out the request indicated.
        self.lock = Lock()

        self.do_render: bool = False
        self.must_update: bool = False

        self.show_mesh: bool = False
        self.mesh_actor: Optional[vtkActor] = None

        logger.debug("Initialized.")

    def queue(self, do_render: bool) -> Thread:
        """Indicates that an update is needed and returns immediately.

        When a mask update is requested while the previous update has yet
        to complete, this function indicates that a new update is needed and
        returns immediately to avoid bogging down the main loop with volume
        loading operations.

        This is the only function that is allowed to start the mask
        updater thread. The mask updater thread can also recursively run
        itself if still needed, as indicated by the must_update flag.
        """

        # Use a lock so multiple queue requests don't race to create the
        # update thread.
        with self.lock:
            self.do_render = do_render
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

        return self.thread

    def _run_thread(self) -> None:
        """The loop for the mask update thread.

        This method will hold lock for as little time as possible since
        this lock has the potential to freeze the UI thread. It should only
        be held while checking and setting the must_update flag.
        """

        try:
            self.lock.acquire()
            while self.must_update:
                self.must_update = False

                # One nice effect of making the mesh first is it will provide
                # quick user feedback since this operation is much faster than
                # generating the whole mask.
                if self.mesh_actor is not None:
                    self.view_frame.remove_actor(self.mesh_actor)
                    self.mesh_actor = None
                    logger.debug("Removed the mesh actor.")
                if self.show_mesh:
                    self.mesh_actor = self.mask.make_mesh()
                    self.view_frame.add_actor(self.mesh_actor)
                    logger.debug("Added the mesh actor.")
                logger.info("Requesting render to show TPS mesh.")
                self.view_frame.vtk_render()
                self.lock.release()

                mask_vtk = self.mask.get_vtk()
                self.view_frame.v_mapper.SetMaskInput(mask_vtk)
                logger.debug("Set volume mask input.")

                self.lock.acquire()

            if self.do_render:
                logger.info("Requesting render.")
                self.view_frame.vtk_render()

            # We can't release the load lock before this method returns or else
            # a must_update flag may be raised and never acted upon.
            self.lock.release()
        except RuntimeError as e:
            logger.exception(f"Thread error: {e}")

    def clear_mask(self) -> None:
        """Remove the mask and mesh actor if needed.

        Thread safe.
        """

        with self.lock:
            if self.mesh_actor is not None:
                self.view_frame.remove_actor(self.mesh_actor)
                self.mesh_actor = None
            self.view_frame.v_mapper.SetMaskInput(None)
