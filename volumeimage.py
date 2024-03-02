import logging
import math
import time
from threading import Lock
from typing import (
    Any,
    NamedTuple,
    Optional,
)

import nrrd  # type: ignore
import numpy as np
import numpy.typing as npt
from vtkmodules.vtkIOImage import vtkImageImport

from errorreporter import FileError

logger = logging.getLogger(__name__)


class ImageBounds(NamedTuple):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


class VolumeImage:
    """Stores a handle to an individual file containing image data.

    Allows access to metadata and rendering data.
    """

    def __init__(self, path: str):
        # Path to the NRRD or NHDR file containing the volume.
        self.path: str = path

        # The raw image data.
        self.image: Optional[npt.NDArray] = None
        self.vtk_image: Optional[vtkImageImport] = None

        # This lock prevents the data from being partially unloaded while it
        # is loading, or vice versa.
        self.load_lock = Lock()
        # The system timestamp for when this volume was last accessed. Used for
        # determining which volume to unload in the timeline.
        self.access_time: float = 0.
        # Used to display the volume info bar.
        self.label: str = ""
        # The header read from the NRRD file.
        self.header: Optional[dict[str, Any]] = None

        self.dtype: Optional[np.dtype] = None
        self.switch_endian: bool = False
        self.dims: Optional[npt.NDArray[np.int_]] = None
        self.origin: npt.NDArray[np.float64] = np.zeros((3,), np.float64)
        self.scale: npt.NDArray[np.float64] = np.ones((3,), np.float64)
        self.period: float = 1.
        self.period_unit: str = "sec"
        self.timestamp: Optional[str] = None
        self.group_index: int = 0
        self.time_index: int = 0
        self.n_times: int = 1

    def read_header(self) -> Optional[FileError]:
        """Attempts to load the NRRD header file.

        Populates relevant values from the header into this object.
        Returns an error message if the header failed to load.
        """

        try:
            logger.debug(f"Reading header from {self.path}...")
            try:
                with np.errstate(all="raise"):
                    header = nrrd.read_header(self.path)
            except StopIteration:
                # There is a bug in the NRRD reader library where empty
                # files will cause the reader to crash with this error.
                return FileError("Blank or corrupt file", self.path)
            except ValueError as e:
                # The NRRD reader cannot handle numeric fields holding text.
                return FileError(f"Invalid header field: {e}", self.path)
            except FloatingPointError as e:
                return FileError(f"Bad numeric data in header field: {e}", self.path)
            except nrrd.NRRDError as e:
                return FileError(f"Invalid NRRD file: {e}", self.path)
            except OSError as e:
                # Either the file doesn't exist, it's already open, or we don't have permission.
                return FileError(f"Failed to open the file: {e}", self.path)

            # Parse the data type to the usual NumPy equivalent so we can check
            # the number of bytes needed to load this into memory before doing so.
            try:
                # This member is protected, but it shouldn't be.
                # noinspection PyProtectedMember
                self.dtype = nrrd.reader._determine_datatype(header)
            except nrrd.NRRDError as e:
                return FileError(f"Invalid NRRD file: {e}", self.path)
            self.switch_endian = not self.dtype.isnative
            if self.switch_endian:
                self.dtype = self.dtype.newbyteorder()
            if self.dtype not in [np.uint8, np.uint16, np.int16]:
                return FileError(f"Pixel data type {self.dtype} is unsupported (uint8, uint16, int16 only)",
                                 self.path)
            # [C,X,Y,Z] array size in pixels.
            self.dims = header["sizes"]
            if self.dims.size not in [3, 4]:
                return FileError(f"{self.dims.size}-D images are not supported (3- or 4-D only)", self.path)
            if self.dims.size == 3:
                self.dims = np.concatenate((np.ones(1, np.int_), self.dims), axis=0)
            n_channels: np.int_ = self.dims[0]
            if n_channels > 4:
                return FileError(f"{n_channels}-channel images are not supported (4 max)", self.path)
            # XYZ voxel dimensions in microns.
            directions: npt.NDArray[np.float64] = header["space directions"]
            if directions.shape == (4, 3):
                # Sometimes directions will be specified for the channel. These can be ignored.
                directions = directions[1:, :]
            elif directions.shape != (3, 3):
                return FileError("The space directions are malformed", self.path)
            # We do not attempt to interpret skew or rotation of the "space directions" matrix.
            self.scale = np.linalg.norm(directions, axis=1)
            if np.any(self.scale <= 0):
                return FileError("The space directions are not positive", self.path)
            # XYZ center offset in pixels.
            if "space origin" in header:
                self.origin = header["space origin"]

            # Custom fields. 5D datasets have a slow and a fast time-axis. The
            # slow axis is the time between acquisition sessions, while the fast
            # axis is within a single acquisition.

            # The slow time-axis index. "scan index" is deprecated;
            # "group index" is the preferred field label.
            try:
                self.group_index = int(header["scan index"])
            except ValueError:
                return FileError(f"Non-integer scan index", self.path)
            except KeyError:
                pass
            try:
                self.group_index = int(header["group index"])
            except ValueError:
                return FileError(f"Non-integer group index", self.path)
            except KeyError:
                pass
            if self.group_index < 0:
                return FileError(f"Negative group index", self.path)
            # The fast time-axis index.
            try:
                self.time_index = int(header["time index"])
            except ValueError:
                return FileError(f"Non-integer time index", self.path)
            except KeyError:
                pass
            if self.time_index < 0:
                return FileError(f"Negative time index", self.path)
            # How many fast timepoints are associated with this slow time
            # point.
            try:
                self.n_times = int(header["n times"])
            except ValueError:
                return FileError(f"Non-integer number of timepoints", self.path)
            except KeyError:
                pass
            if self.n_times < 1:
                return FileError(f"Non-positive number of timepoints (need at least one)", self.path)
            # The slow time-axis. The number of minutes since the initial
            # acquisition.
            try:
                self.timestamp = header["timestamp"]
            except KeyError:
                pass
            if self.timestamp is not None and len(self.timestamp) > 20:
                return FileError(f"Excessively long timestamp ({len(self.timestamp)} characters)", self.path)
            # The length of the short time-axis. How long between this volume
            # acquisition and the next. This is usually constant within a series
            # of acquisitions, and especially within an acquisition.
            try:
                self.period = float(header["period"])
            except ValueError:
                return FileError(f"Non-numeric t1 sample period", self.path)
            except KeyError:
                pass
            if self.period < 0 or math.isnan(self.period) or math.isinf(self.period):
                return FileError(f"Period is not a real number", self.path)
            try:
                self.period_unit = header["period unit"]
            except KeyError:
                pass
            if len(self.period_unit) > 20:
                return FileError(
                    f"Excessively long period unit ({len(self.period_unit)} characters)", self.path)
            self.header = header
            return None  # No error message to report.
        except Exception as e:
            return FileError(f"Uncaught error while parsing header: {e}", self.path)

    def estimate_memory(self) -> int:
        """Estimate how many bytes the file will take if loaded into memory."""

        assert self.header is not None, "You need to call 'read_header' first."
        return self.dtype.itemsize * int(np.product(self.dims))

    def get_scalar_range(self) -> tuple[float, float]:
        """The lowest and highest possible values for this image data type."""

        assert self.header is not None, "You need to call 'read_header' first."
        if self.dtype == np.uint8:
            return 0., 255.
        if self.dtype == np.uint16:
            return 0., 65535.
        if self.dtype == np.int16:
            return -32768., 32767.
        raise RuntimeError(f"Unsupported data type: {self.dtype}.")

    def get_n_channels(self) -> int:
        """The number of independent color channels this volume contains."""

        assert self.header is not None, "You need to call 'read_header' first."
        return int(self.dims[0])

    def load(self) -> Optional[FileError]:
        """Loads the data from the NRRD file into memory.

        Returns an error message if the file was unreadable.
        """

        assert self.header is not None, "You need to call 'read_header' first."

        with self.load_lock:
            if self.is_loaded():
                return None

            logger.info(f"Loading data from {self.path}...")
            try:
                # Transposing an array is slow, so we store it in the native
                # format: [Z,Y,X,C]. The axis order needs to be inverted because
                # we use C-style indexing rather than Fortran-style indexing.
                self.image, header = nrrd.read(self.path, index_order="C")
            except StopIteration:
                # There is a bug in the NRRD reader library where empty
                # files will cause the reader to crash with this error.
                return self._fail_load("Blank or corrupt file")
            except ValueError as e:
                # The NRRD reader cannot handle numeric fields holding text.
                return self._fail_load(f"Invalid header field: {e}")
            except FloatingPointError as e:
                return self._fail_load(f"Bad numeric data in header field: {e}")
            except nrrd.NRRDError as e:
                return self._fail_load(f"Invalid NRRD file: {e}")
            except OSError as e:
                # Either the file doesn't exist, it's already open, or we don't have permission.
                return self._fail_load(f"Failed to open the file: {e}")

            assert self.image is not None, "The NRRD reader failed silently and returned None."

            # Check that the data is at least the same shape as what we expected.
            # It is still possible for a different file to be loaded than the one whose header was read,
            # but at least it will be the same size and data type.
            if (self.header["type"] != header["type"]
                    or self.header["sizes"].shape != header["sizes"].shape
                    or np.any(self.header["sizes"] != header["sizes"])):
                return self._fail_load("File has changed since the header was initially read")

            # Channel-less images need to reshaped to have one channel.
            if len(self.image.shape) == 3:
                self.image = self.image.reshape(self.dims)
            # The endianness needs to be native for VTK to display properly.
            if self.switch_endian:
                self.image.byteswap(True)
            self._make_vtk_image()

        # No error message to report.
        return None

    def _fail_load(self, message: str) -> FileError:
        """Sets up the image with a default array when loading it fails.

        Returns an error message object to be passed along.
        """

        self.image = np.zeros(self.dims, np.uint8)
        self._make_vtk_image()
        return FileError(message, self.path)

    def _make_vtk_image(self) -> None:
        """Create the VTK image data object for viewing."""

        self.vtk_image = vtkImageImport()
        self.vtk_image.SetImportVoidPointer(self.image.ravel())
        if self.dtype == np.uint8:
            self.vtk_image.SetDataScalarTypeToUnsignedChar()
        elif self.dtype == np.uint16:
            self.vtk_image.SetDataScalarTypeToUnsignedShort()
        elif self.dtype == np.int16:
            self.vtk_image.SetDataScalarTypeToShort()
        else:
            raise RuntimeError("It is supposed to be impossible to set the wrong data type.")
        self.vtk_image.SetNumberOfScalarComponents(self.dims[0])
        self.vtk_image.SetDataExtent(
            0, self.dims[1] - 1,
            0, self.dims[2] - 1,
            0, self.dims[3] - 1
        )
        self.vtk_image.SetWholeExtent(
            0, self.dims[1] - 1,
            0, self.dims[2] - 1,
            0, self.dims[3] - 1
        )
        self.vtk_image.SetDataSpacing(self.scale)
        self.vtk_image.SetDataOrigin(self.origin)
        # By keeping a handle to the underlying array data, we can avoid
        # VTK access violations related to premature garbage collection.
        self.vtk_image._array_data = self.image

    def unload(self) -> None:
        """Frees the memory containing the image data.

        The memory will be freed only when the garbage collector decides to,
        so this is a safe operation.
        """

        with self.load_lock:
            self.image = None
            self.vtk_image = None

    def is_loaded(self) -> bool:
        """Determines if the data in this volume has been loaded from disk."""

        return self.image is not None

    def get_phase(self) -> float:
        """Calculate the fraction of the cycle this timepoint represents."""

        return self.time_index / self.n_times

    def make_label(self, time_sum: float, index: int, n_volumes: int) -> None:
        """Create the label used for the timeline info tag.

        :param time_sum: The cumulative cyclic time of this volume.
        :param index: The volume index within the timeline.
        :param n_volumes: The total number of volume in the timeline.
        """

        timestamp = str(self.group_index)
        if self.timestamp is not None:
            timestamp += " (" + self.timestamp + ")"

        self.label = (
            f"φ = {self.get_phase():.1%}, "
            f"t1 = {self.time_index}/{self.n_times} ({time_sum:0.3f} {self.period_unit}), "
            f"t2 = {timestamp}, "
            f"i = {index + 1}/{n_volumes}"
        )

    def get_vtk_image(self) -> vtkImageImport:
        """Returns a handle to the VTK image."""

        self.access_time = time.time()
        self.load()
        return self.vtk_image

    def get_bounds(self) -> ImageBounds:
        """The min and max extents of the image in VTK world coordinates."""

        assert self.header is not None, "You need to call 'read_header' first."

        lower = self.origin
        upper = self.origin + self.scale * self.dims[1:]
        return ImageBounds(
            lower[0], upper[0],
            lower[1], upper[1],
            lower[2], upper[2]
        )

    def get_view_scale(self) -> float:
        """Determines the window scale that will fit this volume.

        The number returned will become half the viewport height in microns.
        """

        assert self.header is not None, "You need to call 'read_header' first."
        return 1.5 * np.max(self.scale * self.dims[1:]) / 2
