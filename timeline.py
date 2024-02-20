import logging
import time
from threading import (
    Thread,
    Lock,
)
from typing import (
    Callable,
    Optional,
    Protocol,
    Tuple,
)

import numpy as np
import numpy.typing as npt

from errorreporter import (
    FileError,
    ErrorReporter,
)
from volumeimage import (
    ImageBounds,
    VolumeImage,
)

logger = logging.getLogger(__name__)
logger_load = logging.getLogger(__name__ + ".load")
logger_cache = logging.getLogger(__name__ + ".cache")


class Threader(Protocol):
    """A threader has a 'thread' attribute which might be None.

    This is intended for a low-priority daemon that ought to wait for
    other threads to finish before it does its job to avoid resource use.
    """

    thread: Optional[Thread]


class Timeline:
    """Arranges and manages the list of volumes in the 5D timeline.

    Keeps track of:
    * The list of all volumes.
    * The current volume.
    * The memory usage of all volumes.

    Does:
    * Decode lists of file paths into an internal list of volumes.
    * Ask volumes to load themselves into memory on an as-needed basis.
    * Unload volumes as needed to keep under the memory limit.
    * Preemptively cache volumes via a daemon thread.
    * Ask volumes to store labels to be retrieved for viewing.

    Threads:
    * Cache
    * UI

    Typical use:
      timeline = Timeline()
      timeline.set_file_paths(list_paths)
      timeline.set_priority_threaders()
      timeline.start_caching()
    """

    def __init__(self,
                 error_reporter: ErrorReporter,
                 memory_target: int = 0) -> None:
        self.error_reporter: ErrorReporter = error_reporter
        # This can be dynamically changed to any value, but if you shrink
        # it, it might not respond until you request a volume to be loaded.
        self.memory_target: int = memory_target
        # Prevents multiple threads from loading volumes into memory
        # simultaneously. That would result in inaccurate memory usage
        # reports and potentially more volumes in memory than permitted.
        self.load_lock = Lock()
        # While the contents of the timeline are changing, it is impermissible
        # to access the volumes. This is implemented via a readers-writer lock.
        # TODO: self.rw_lock = ...
        self.index: int = 0
        self.volumes: list[VolumeImage] = []
        # Bytes of memory used (estimate). Do not edit this estimate without
        # a load lock in place to ensure it remains accurate.
        self.memory_used: int = 0
        # True when one or more volumes have been added and had their
        # headers read successfully.
        self.available: bool = False
        self.priority_threaders: list[Threader] = []
        self.cache_thread: Optional[Thread] = None

    def __len__(self) -> int:
        """The number of volumes this timeline manages."""

        return len(self.volumes)

    def __bool__(self) -> bool:
        """A Timeline is True when it has volumes available for use."""

        return self.available

    def set_file_paths(
            self,
            file_paths: list[str],
            progress_callback: Optional[Callable[[int], bool]] = None) -> list[FileError]:
        """Set up the volumes given a list of files, one for each volume.

        This may be a slow method call since, potentially, thousands of
        files need to be touched. As such, you can pass a progress callback
        which will periodically be called with the number of volume headers
        read as its argument and returns whether to cancel the operation.

        The labels are also generated here and stored in each volume image.
        """

        assert file_paths, "No file paths were passed."
        logger.debug("set_file_paths")
        file_errors: list[FileError] = []
        volumes: list[VolumeImage] = list(map(VolumeImage, file_paths))

        # All the volumes need to read their corresponding headers to
        # populate the metadata.
        volume_error_indices: list[int] = []
        for i, v in enumerate(volumes):
            error_msg = v.read_header()
            if error_msg is not None:
                logger.debug(f"Error read volume[{i}] at '{v.path}': {error_msg[0]}")
                # Note the error and flag the volume for removal.
                file_errors.append(error_msg)
                volume_error_indices.append(i)
            else:
                logger.debug(f"Successfully read volume[{i}] at '{v.path}'")

            # Update a status bar if there is one.
            if progress_callback is not None and progress_callback(i + 1):
                # If the loading operation is canceled, we will still
                # have at least one volume loaded, so we can continue as
                # usual.
                volumes = volumes[:i + 1]
                break

        # Get rid of any erroneous volumes.
        for i in reversed(volume_error_indices):
            logger.debug(f"Removing index {i} at {volumes[i].path}")
            del volumes[i]

        # Sort volumes increasing first by scan index, the slow time axis.
        volumes.sort(key=lambda vol: (vol.scan_index, vol.time_index))

        # Compute the time integral and label the volumes.
        scan_index: Optional[int] = None
        time_sum: float = 0
        for i, v in enumerate(volumes):
            if v.scan_index != scan_index:
                scan_index = v.scan_index
                # Times are accumulated only for each scan.
                time_sum = 0
            v.make_label(time_sum, i, len(volumes))
            time_sum += v.period

        # The daemon threads might be running if this is called a second
        # time with a new list of files, so it needs to be locked.
        with self.load_lock:
            if len(volumes) > 0:
                # The "open" operation was successful.
                # Explicitly unload any old volumes so their locks work correctly
                # to prevent freeing a volume that is in active use by another thread.
                for v in self.volumes:
                    v.unload()
                self.volumes = volumes
                # This is mostly safe to zero because Python will free the
                # unreferenced volume images after the old volume list is
                # destroyed, however the rendered volume will stick around for a
                # while longer. Luckily, this is only an *estimate* of memory
                # usage.
                self.memory_used = 0
                # Create the index of the "current" volume and ensure the cache
                # priorities have been established.
                self.seek(0)
                # The timeline can never become unavailable once made available.
                self.available = True
                logger.info("Volumes are now available.")
            else:
                logger.info("All loaded volumes were erroneous.")

        return file_errors

    def seek(self, index: int) -> None:
        """Set the current volume to the given index.

        As a consequence, the volume cache priorities must be updated."""

        assert self.volumes, "You need to call set_file_paths first."

        self.index = index
        self._make_cache_priorities()
        logger.info(f"Timeline: Sought {index}.")

    def get(self,
            index: Optional[int] = None,
            preload: bool = True) -> VolumeImage:
        """Return the volume at 'index', if given, otherwise the current volume.

        When preload is true, ensures that volume data has been loaded into
        memory before returning it. Do not call this method before
        populating with volumes.
        """

        assert self, "You need to call set_file_paths first."

        if index is None:
            index = self.index
        logger.debug(f"Getting volume {index}. Preload? {preload}")
        if preload:
            self._load_volume(index)
        return self.volumes[index]

    def _load_volume(self, index: int) -> None:
        """Loads the volume at the index specified into memory.

        The memory usage is checked against the target and unloading of
        less valuable volumes is performed if necessary.
        """

        assert self, "You need to call set_file_paths first."

        with self.load_lock:
            logger_load.info(f"Trying to load volume {index}.")
            vol: VolumeImage = self.volumes[index]
            if vol.is_loaded():
                logger_load.info(f"Already loaded {index}.")
                return

            self.memory_used += vol.estimate_memory()
            for v in sorted(filter(lambda vo: vo.is_loaded(), self.volumes),
                            key=lambda vo: vo.access_time):
                if self.memory_used <= self.memory_target:
                    break
                # Find the memory before you unload because the estimate
                # changes when the mask is unloaded.
                memory_recovered = v.estimate_memory()
                v.unload()
                self.memory_used -= memory_recovered
                logger_load.debug(f"Unloaded volume S{v.scan_index}T{v.time_index} \
last accessed at {v.access_time:.3f} and recovered {memory_recovered:0.2g} bytes.")

            error_message = vol.load()
            if error_message is not None:
                self.error_reporter.file_errors([error_message])
            logger_load.info(f"Loaded {index}.")

    def unload_volume(self, index: int) -> None:
        """Unloads the volume at 'index'."""

        assert self, "You need to call set_file_paths first."

        v = self.volumes[index]
        with self.load_lock:
            v.unload()
            self.memory_used -= v.estimate_memory()

    def get_prev_scan_index(self) -> int:
        """The index of the volume with a scan index less than the current scan
        index and the closest matching phase. The lower index breaks ties."""

        assert self, "You need to call set_file_paths first."

        i = self.index
        scan_index = self.volumes[i].scan_index
        phase = self.volumes[i].get_phase()
        while i > 0 and scan_index == self.volumes[i].scan_index:
            i -= 1
        scan_index = self.volumes[i].scan_index
        smallest_diff: float = 1.
        i_best: int = i
        while i >= 0 and scan_index == self.volumes[i].scan_index:
            diff: float = abs(phase - self.volumes[i].get_phase())
            if diff > 0.5:
                diff = 1 - diff
            if diff <= smallest_diff:
                smallest_diff = diff
                i_best = i
            i -= 1
        logger.debug(f"Prev. to scan index {scan_index} from i = {self.index} to {i_best} and phase = "
                     f"{phase} to best match of {self.volumes[i_best].get_phase()}")
        return i_best

    def get_next_scan_index(self) -> int:
        """The index of the volume with a scan index less than the current scan
        index and the closest matching phase, if available, otherwise the
        lowest-indexed volume.

        The index of the first volume with a scan index greater than
        the current scan index.

        This method is intended to be called when skipping around the
        timeline from one scan to the next.
        """

        assert self, "You need to call set_file_paths first."

        i = self.index
        scan_index = self.volumes[i].scan_index
        phase = self.volumes[i].get_phase()
        i_max = len(self.volumes) - 1
        while i < i_max and scan_index == self.volumes[i].scan_index:
            i += 1
        scan_index = self.volumes[i].scan_index
        smallest_diff: float = 1.
        i_best: int = i
        while i <= i_max and scan_index == self.volumes[i].scan_index:
            diff: float = abs(phase - self.volumes[i].get_phase())
            if diff > 0.5:
                diff = 1 - diff
            if diff <= smallest_diff:
                smallest_diff = diff
                i_best = i
            i += 1
        logger.debug(f"Next to scan index {scan_index} from i = {self.index} to {i_best} and phase = "
                     f"{phase} to best match of {self.volumes[i_best].get_phase()}")
        return i_best

    def get_first_scan_index(self) -> int:
        """The lowest index of the volume with a scan index equal to the current scan."""

        assert self, "You need to call set_file_paths first."

        # It's good practice to make a local copy of the current index so
        # the other threads can't change it in the middle of the operation.
        i = self.index
        scan_index = self.volumes[i].scan_index
        while i > 0 and scan_index == self.volumes[i-1].scan_index:
            i -= 1
        logger.debug(f"First to scan index {scan_index} from i = {self.index} to {i}, "
                     f"S{self.volumes[i].scan_index}T{self.volumes[i].time_index}")
        return i

    def get_last_scan_index(self) -> int:
        """The highest index of the volume with a scan index equal to the current scan."""

        assert self, "You need to call set_file_paths first."

        # It's good practice to make a local copy of the current index so
        # the other threads can't change it in the middle of the operation.
        i = self.index
        scan_index = self.volumes[i].scan_index
        while i < len(self.volumes) - 1 and scan_index == self.volumes[i+1].scan_index:
            i += 1
        logger.debug(f"Last to scan index {scan_index} from i = {self.index} to {i}, "
                     f"S{self.volumes[i].scan_index}T{self.volumes[i].time_index}")
        return i

    def _make_cache_priorities(self) -> None:
        """Calculates a sorted list of cache priorities, indicesByCachePriority.

        Cache priorities are assigned based on proximity to the active
        volume. Subsequent volumes are prioritized over previous volumes.
        """

        assert self.volumes, "You need to call set_file_paths first."

        # It's good practice to make a local copy of the current index so
        # the other threads can't change it in the middle of the operation.
        index = self.index

        relative_index = np.arange(len(self.volumes)) - index
        # By the magic of modulo, these always represent the positive
        # distance in front or behind while accounting for wrap-around.
        forward_distances = relative_index % len(self.volumes)
        backward_distances = (-relative_index) % len(self.volumes)

        # The multiplier on the forward distance is called the "forward
        # bias". It is approximately the number of forward-looking volumes
        # that go ahead of each backward-looking volume in the queue.
        # The addition of 1 smooths the metric a little and prevents division by 0.
        cache_priorities = 4 / (1 + forward_distances) + 1 / (1 + backward_distances)

        self.indices_by_cache_priority = list(range(len(self.volumes)))
        self.indices_by_cache_priority.sort(key=lambda i: cache_priorities[i],
                                            reverse=True)

    def get_label(self) -> str:
        """The label attached to the current volume.

        This represents the timestamp, phase info, etc. associated with the
        volume.
        """

        assert self, "You need to call set_file_paths first."
        return self.volumes[self.index].label

    def set_priority_threaders(self, priority_threaders: list[Threader]) -> None:
        """Assign a list of objects containing a 'thread' attribute.

        The cache daemon will not run while the thread contained in each
        suspender runs. As such, these threads are 'high priority'.
        """

        self.priority_threaders = priority_threaders

    def start_caching(self) -> None:
        """Creates and starts the volume caching thread.

        This thread preemptively loads volumes into memory but is not
        required to free memory. Freeing memory is performed by the
        "_load_volume" method.

        You need to call 'set_priority_threaders' first, but setting the
        initial volumes in unnecessary.
        """

        self.cache_thread = Thread(target=self._run_cache, daemon=True)
        self.cache_thread.start()

    def _run_cache(self) -> None:
        """Load volumes in the background, highest priority first."""

        assert self.cache_thread is not None, \
            "You need to call start_caching first."

        try:
            logger_cache.info("Started.")
            while True:
                # Verify that no threads are running whose operation would
                # be slowed by this cache thread loading an extra volume.
                # This is not race-condition-proof, but a race-condition
                # here is unlikely to happen, and the worst-case result is a
                # momentary lag in the volume loader.
                for pt in self.priority_threaders:
                    t = pt.thread
                    if t and t.is_alive():
                        t.join()
                        continue

                if not self:
                    # No volumes have been added, so there is nothing to do yet.
                    logger_cache.info("No volumes are available.")
                    self._cache_daemon_sleep()
                    continue

                if self.memory_used >= self.memory_target:
                    # The memory is full. Check again later.
                    logger_cache.info(f"Memory full: {self.memory_used:0.2g}/{self.memory_target:0.2g}.")
                    self._cache_daemon_sleep()
                    continue

                for i in self.indices_by_cache_priority:
                    v: VolumeImage = self.volumes[i]
                    if not v.is_loaded():
                        logger_cache.info(f"Caching volume {i}, memory is at \
{self.memory_used:0.2g}/{self.memory_target:0.2g}..")
                        with self.load_lock:
                            v.load()
                            self.memory_used += v.estimate_memory()
                        logger_cache.info(f"Caching volume {i} done. Added \
{v.estimate_memory():0.2g} memory.")
                        break
                else:
                    # No volume worth loading. Check again later.
                    logger_cache.info("No volume worth loading.")
                    self._cache_daemon_sleep()
        except RuntimeError as e:
            logger_cache.exception(f"Thread error: {e}")

    @staticmethod
    def _cache_daemon_sleep() -> None:
        """Sleep for the standard idle time."""

        time.sleep(5)

    def check_memory(self) -> Tuple[int, int]:
        """Check the memory to verify that the memory tally is correct.

        This mainly exists for debugging.
        """

        if not self:
            return 0, 0

        n_loaded: int = 0
        actual_memory_used: int = 0
        for i, v in enumerate(self.volumes):
            if v.is_loaded():
                logger.info(f"Check memory: volumes[{i}] is loaded.")
                n_loaded += 1
                actual_memory_used += v.estimate_memory()
        logger.info(f"Check memory: {n_loaded} volumes are loaded taking \
{actual_memory_used:0.2g} as compared to {self.memory_used:0.2g} tallied.")
        return n_loaded, actual_memory_used

    def extreme_bounds(self) -> ImageBounds:
        """Find the bounds that encompass all volumes in the timeline."""

        assert self, "You need to call set_file_paths first."

        with self.load_lock:
            # Rearrange bounds.
            bounds = list(zip(*(v.get_bounds() for v in self.volumes)))
            return ImageBounds(
                min(bounds[0]), max(bounds[1]),
                min(bounds[2]), max(bounds[3]),
                min(bounds[4]), max(bounds[5])
            )

    def min_scale(self) -> npt.NDArray[np.float64]:
        """Find the smallest scale for each axis across all volumes."""

        assert self, "You need to call set_file_paths first."

        with self.load_lock:
            all_scales = np.array([v.scale for v in self.volumes])
            return np.min(all_scales, axis=0)

    def max_voxels(self) -> np.uint64:
        """Find the largest number of voxels across all volumes."""

        assert self, "You need to call set_file_paths first."

        with self.load_lock:
            all_dims = np.array([v.dims[1:] for v in self.volumes],
                                dtype=np.uint64)
            return all_dims.prod(axis=1).max()

    def get_view_scale(self) -> float:
        """Determines the window scale that will fit the current volume.

        The number returned will become half the viewport height in microns.
        """

        assert self, "You need to call set_file_paths first."
        return self.volumes[self.index].get_view_scale()

    def get_scan_lengths(self) -> list[int]:
        """Count the number of volumes for each scan in the timeline.

        :return: A list of the number of volumes in each sequential scan.
            Example: [70, 70, 73, 66, ...]
        """

        scan_lengths: list[int] = []
        with self.load_lock:
            if not self:
                return scan_lengths

            last_scan_index = self.volumes[0].scan_index
            last_len: int = 1
            for v in self.volumes[1:]:
                if last_scan_index != v.scan_index:
                    scan_lengths.append(last_len)
                    last_scan_index = v.scan_index
                    last_len = 0
                last_len += 1
        if last_len > 0:
            scan_lengths.append(last_len)
        return scan_lengths
