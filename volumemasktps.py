from enum import IntEnum
import logging
from threading import Lock
from typing import (
    Optional,
    Sequence,
)

import numpy as np
import numpy.typing as npt
from scipy.spatial.distance import cdist  # type: ignore
from vtkmodules.vtkCommonCore import (
    vtkDataArray,
    vtkPoints,
    VTK_UNSIGNED_CHAR,
)
from vtkmodules.vtkCommonDataModel import (
    vtkImageData,
    vtkStructuredGrid,
)
from vtkmodules.vtkFiltersGeometry import vtkStructuredGridGeometryFilter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkProperty,
)

from sceneitems.controlpoint import ControlPoint
from volumeimage import (
    VolumeImage,
)

logger = logging.getLogger(__name__)


class MaskUpdate(IntEnum):
    """Enumerates the state of progress towards a complete mask computation.

    Levels of "dirtiness" in decreasing order:
      0. Full: Generate the mask from the beginning.
      1. Partial: The shape of the mask is the same, so only the difference
        in needs to be updated.
      2. None: No update needed.
    """

    FULL = 0
    PARTIAL = 1
    NONE = 2


class VolumeMaskTPS:
    """Stores and calculates the volume mask using a thin-plate spline (TPS).

    Operates an independent thread so that control point updates and such
    can be requested in a non-blocking manner.

    Calculation flow each time a control point is updated:
      Control points -> phi -> dependent variable grid -> resample -> mask
    """

    def __init__(self) -> None:
        self.axis: int = 0
        self.keep_greater_than: bool = False
        self.regularization: float = 0.
        self.upscale: float = 1.
        # The list of control points associated with the UI.
        self.control_points: list[ControlPoint] = []
        # The Nx3 array of points in world space that control the surface.
        # There is a one-to-one correspondence between these and "self.control_points".
        self.control_array: npt.NDArray[np.float32] = np.empty((0, 3), np.float32)

        self._mask_update: MaskUpdate = MaskUpdate.FULL
        self.parameters: Optional[npt.NDArray[np.float32]] = None
        self.dep_indices: Optional[npt.NDArray[np.uint32]] = None
        self.mask: Optional[npt.NDArray[np.uint8]] = None
        self.vtk_data: Optional[vtkImageData] = None

        # Volume info:
        self.v_dims: Optional[npt.NDArray[np.uint64]] = None
        self.v_offset: Optional[npt.NDArray[np.float32]] = None
        self.v_scale: Optional[npt.NDArray[np.float32]] = None

        # Acquire this whenever you modify one on the inputs to mask generation,
        # such as the axis or the control points.
        self.lock: Lock = Lock()
        # Only one thread is allowed to generate the mask at a time.
        self.get_vtk_lock: Lock = Lock()

    def has_volume(self) -> bool:
        """True after set_volume has completed the first time."""

        return (self.v_dims is not None
                and self.v_scale is not None
                and self.v_offset is not None)

    def _reduce_progress(self, new_state: MaskUpdate) -> None:
        """Set the mask update status to at most the level given.

        You must hold "self.lock" while calling this method to avoid race
        conditions.
        """

        logger.debug(f"_reduce_progress: {self._mask_update} -> {new_state}")
        self._mask_update = min(self._mask_update, new_state)

    def set_axis(self, axis: int) -> None:
        """Set the dependent variable index and update the dirtiness.

        Thread safe.

        Axes:
          0 = X
          1 = Y
          2 = Z
        """

        with self.lock:
            logger.debug(f"set_axis({axis})")
            if self.axis != axis:
                self.axis = axis
                self.parameters = None
                self._reduce_progress(MaskUpdate.FULL)
            else:
                logger.debug("set_axis deemed unnecessary.")

    def set_direction(self, keep_greater_than: bool) -> None:
        """Set which direction to show in the mask and update the dirtiness.

        Thread safe.
        """

        with self.lock:
            logger.debug(f"set_direction({keep_greater_than})")
            if self.keep_greater_than != keep_greater_than:
                self.keep_greater_than = keep_greater_than
                self._reduce_progress(MaskUpdate.FULL)
            else:
                logger.debug("set_direction deemed unnecessary.")

    def set_regularization(self, regularization: float) -> None:
        """Update the regularization parameter and the dirtiness.

        Regularization "alpha" or "lambda" varies from [0.0-1.0] and
        determines now closely to track the control points vs. how smoothly
        to fit the surface by reducing the net curvature.

        Thread safe.
        """

        with self.lock:
            logger.debug(f"set_regularization({regularization})")
            if self.regularization != regularization:
                self.regularization = regularization
                self.parameters = None
                self._reduce_progress(MaskUpdate.PARTIAL)
            else:
                logger.debug("set_regularization deemed unnecessary.")

    def set_upscale(self, upscale: float) -> None:
        """Update the up-scale parameter and the dirtiness.

        Up-scale is a number ranging from 1 to infinity. It determines the size
        of the mask relative to the size of the volume, as mask = volume/upscale.
        This is rounded so that the mask cannot have zero width no matter how
        large up-scale is.

        Thread safe.
        """

        with self.lock:
            logger.debug(f"set_upscale({upscale})")
            if self.upscale != upscale:
                self.upscale = upscale
                self._reduce_progress(MaskUpdate.FULL)
            else:
                logger.debug("set_upscale deemed unnecessary.")

    def _independent_axes(self) -> npt.NDArray[np.int_]:
        """Get the two remaining axes perpendicular to self.axis.

        E.g.: if "self.axis" = 1 (dependent axis) -> return [0, 2]

        You must hold "self.lock" while calling this method to avoid race
        conditions.
        """

        ijk = np.arange(3)
        axis = self.axis
        return np.hstack((ijk[:axis], ijk[axis + 1:]))

    def _fit(self) -> npt.NDArray[np.float32]:
        """Make "parameters" object by fitting the control points.

        Called by functions updating the control points. This is very fast
        for reasonable numbers of control points, but the computational
        complexity grows on the order of O(n^3).

        You must hold "self.lock" while calling this method to avoid race
        conditions.
        """

        assert self.control_array.shape[0] >= 3, "Need at least 3 control points to fit a mask."

        # We know the parameters are out of date when they have been nullified.
        if self.parameters is not None:
            return self.parameters

        # Signal that the parameters have changed recently.
        self.params_updated = True

        logger.debug("Fitting parameters...")
        # Axes for the independent variables only.
        ia = self._independent_axes()
        ctrl_ind = self.control_array[:, ia]
        ctrl_dep = self.control_array[:, self.axis].reshape((-1, 1))

        n = self.control_array.shape[0]
        phi_ctrl = _radial_distance(ctrl_ind, ctrl_ind)

        # Build the linear system AP = Y
        X = np.hstack([np.ones((n, 1), np.float32), ctrl_ind])
        A = np.vstack([
            np.hstack([phi_ctrl + self.regularization * np.eye(n, dtype=np.float32), X]),
            np.hstack([X.T, np.zeros((3, 3), np.float32)])
        ])
        y = np.vstack([
            ctrl_dep,
            np.zeros((3, 1), np.float32)
        ])
        try:
            self.parameters = np.linalg.solve(A, y)
            logger.debug("Parameters fit.")
        except np.linalg.LinAlgError as e:
            self.parameters = np.zeros((A.shape[1], 1), np.float32)
            logger.warning(f"Parameter fitting failed: {e}")
        return self.parameters

    def count_cp(self) -> int:
        """Return the number of control points contributing to this spline."""

        assert len(self.control_points) == self.control_array.shape[0], \
            "Number of control points is inconsistent with the control array."
        return len(self.control_points)

    def add_cp(self, cp: ControlPoint) -> None:
        """Add the passed control point and update the dirtiness.

        Fast enough to operate on the UI thread.

        Thread safe.
        """

        with self.lock:
            logger.debug(
                f"Add CP:, {cp.get_origin()} Shape: {self.control_array.shape}"
            )
            a = np.array(cp.get_origin(), np.float32)
            self.control_array = np.vstack((self.control_array, a))
            self.control_points.append(cp)
            self.parameters = None
            self._reduce_progress(MaskUpdate.PARTIAL)

    def delete_cp(self, cp: ControlPoint) -> None:
        """Remove the passed control point and update the dirtiness.

        Fast enough to operate on the UI thread.

        Thread safe.
        """

        with self.lock:
            i = self.control_points.index(cp)
            i_last = self.control_array.shape[0] - 1
            logger.debug(f"Deleting control_point[{i}]. Last index: {i_last}.")
            if i != i_last:
                # Swap ...
                logger.debug(f"Control point to delete isn't last.")
                # Replace the deleted row with the last row so we can crop off the end.
                self.control_points[i] = self.control_points[i_last]
                self.control_array[i] = self.control_array[i_last]
            # ... and pop.
            self.control_points.pop()
            self.control_array = self.control_array[:i_last, :]
            self.parameters = None
            self._reduce_progress(MaskUpdate.PARTIAL)

    def update_cp(self, cp: ControlPoint) -> None:
        """Update the passed control point and update the dirtiness.

        Fast enough to operate on the UI thread.

        Thread safe.
        """

        with self.lock:
            i = self.control_points.index(cp)
            logger.debug(f"Updating control_point[{i}].")
            a = np.array(cp.get_origin(), np.float32)
            self.control_array[i, :] = a
            self.parameters = None
            self._reduce_progress(MaskUpdate.PARTIAL)

    def set_volume(self, volume: VolumeImage) -> None:
        """Read the volume metadata.

        Thread safe.
        """

        assert volume.dims is not None, "Volume header wasn't read."
        assert volume.origin is not None, "Volume header wasn't read."
        assert volume.scale is not None, "Volume header wasn't read."

        with self.lock:
            v_dims = volume.dims[1:].astype(np.uint64)
            v_offset = volume.origin.astype(np.float32)
            v_scale = volume.scale.astype(np.float32)
            logger.debug("set_volume:")
            logger.debug(f"{v_dims=}")
            logger.debug(f"{v_offset=}")
            logger.debug(f"{v_scale=}")
            # Shape: XYZ
            assert v_dims.shape == (3,), "'v_dims' must be 3D."
            assert v_offset.shape == (3,), "'v_offset' must be 3D."
            assert v_scale.shape == (3,), "'v_scale' must be 3D."

            # We can do a partial update if the dimensions are the same, or no
            # update at all if the volume is in the same location as the last.
            same_volume: np.bool_ = np.bool_(
                np.all(v_dims == self.v_dims)
                and np.all(v_offset == self.v_offset)
                and np.all(v_scale == self.v_scale)
            )
            if not same_volume:
                self._reduce_progress(
                    MaskUpdate.PARTIAL
                    if np.all(v_dims == self.v_dims)
                    else MaskUpdate.FULL)
                self.v_dims = v_dims
                self.v_offset = v_offset
                self.v_scale = v_scale

    # The constant NxN number of vertices to construct a mesh out of.
    N_MESH: int = 16

    def make_mesh(self) -> vtkActor:
        """Build an actor to represent the surface as a mesh.

        The actor must be added on the UI thread holding the OpenGL context
        or else an error will occur.

        Thread safe.
        """

        # Should be set once and done. No need to lock.
        assert self.has_volume(), "Didn't load a volume."

        # Get everything ready so we don't need to access any more
        # attributes that might change on another thread.
        with self.lock:
            axis = self.axis
            ia = self._independent_axes()
            # World coordinates.
            i_lower = self.v_offset[ia]
            i_upper = i_lower + self.v_scale[ia] * self.v_dims[ia]
            i_ctrl = self.control_array[:, ia]
            parameters = self._fit()

        # The rest of this doesn't need to be locked.

        a0, a1 = _make_grid_axes(i_lower, i_upper, (self.N_MESH, self.N_MESH))
        dep_var = _make_dep_var(a0, a1, parameters, i_ctrl)

        # Make a VTK mesh.
        points = vtkPoints()
        points.SetDataTypeToFloat()
        points.SetNumberOfPoints(self.N_MESH * self.N_MESH)
        if axis == 0:
            for i in range(self.N_MESH):
                for j in range(self.N_MESH):
                    points.SetPoint(i * self.N_MESH + j, dep_var[j, i], a0[0, i], a1[j, 0])
        elif axis == 1:
            for i in range(self.N_MESH):
                for j in range(self.N_MESH):
                    points.SetPoint(i * self.N_MESH + j, a0[0, i], dep_var[j, i], a1[j, 0])
        elif axis == 2:
            for i in range(self.N_MESH):
                for j in range(self.N_MESH):
                    points.SetPoint(i * self.N_MESH + j, a0[0, i], a1[j, 0], dep_var[j, i])
        else:
            raise RuntimeError("Axis is outside range(3).")

        mesh = vtkStructuredGrid()
        mesh_dims = [self.N_MESH] * 3
        mesh_dims[axis] = 1
        mesh.SetDimensions(mesh_dims)
        mesh.SetPoints(points)

        # Filter produces vtkPolyData for the mapper.
        geo = vtkStructuredGridGeometryFilter()
        geo.SetInputData(mesh)
        # noinspection PyArgumentList
        geo.Update()

        mapper = vtkPolyDataMapper()
        mapper.SetInputData(geo.GetOutput())

        prop = vtkProperty()
        prop.SetRepresentationToWireframe()
        prop.SetColor(1, 1, 0)  # Yellow
        prop.SetLineWidth(2)

        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetProperty(prop)

        return actor

    def _make_mask(self) -> npt.NDArray[np.uint8]:
        """Generate the mask array.

        Make an appropriately sized view into the allocated mask array and
        fill it with transparent or opaque values depending on whether it is
        above or below the clipping surface defined by the dependent variable.

        You must hold self.gen_VTK_lock while calling this method to avoid
        race conditions.
        """

        assert self.has_volume(), "Didn't load a volume."

        with self.lock:
            # Make copies of variables to prevent them from changing during
            # thread operation.
            mask_update = self._mask_update
            if mask_update == MaskUpdate.NONE:
                logger.info("The mask doesn't need updating.")
                return self.mask
            self._mask_update = MaskUpdate.NONE

            v_dims_f = np.ceil(self.v_dims.astype(np.float32) / self.upscale)
            v_dims = v_dims_f.astype(np.uint64)
            # Since we adjusted the dims, the scale needs to be larger too.
            # We would just multiply by `upscale`, but this avoids rounding error.
            v_scale = self.v_scale * (self.v_dims.astype(np.float32) / v_dims_f)
            axis = self.axis
            a_offset = self.v_offset[axis]
            a_scale = v_scale[axis]
            a_dim = v_dims[axis]

            ia = self._independent_axes()
            i_ctrl = self.control_array[:, ia]
            # World coordinates.
            i_lower = self.v_offset[ia]
            i_step = v_scale[ia]
            i_dims = v_dims[ia]
            i_upper = i_lower + i_step * i_dims

            # This operation is usually computationally cheap, and the other
            # thread will need this to be generated in any case.
            parameters = self._fit()

        logger.info(f"Rebuilding the spline grid for axis {axis}...")
        a0, a1 = _make_grid_axes(i_lower, i_upper, i_dims)
        dep_var = _make_dep_var(a0, a1, parameters, i_ctrl)
        dep_indices = np.clip(
            ((dep_var - a_offset) / a_scale).astype(np.int_),
            0, a_dim
        )

        if self.keep_greater_than:  # Only accessed once; is thread safe.
            fill_below = np.uint8(0)  # Transparent
            fill_above = np.uint8(255)  # Opaque
        else:
            fill_below = np.uint8(255)  # Opaque
            fill_above = np.uint8(0)  # Transparent

        if self.mask is not None:
            logger.debug(f"{self.mask.shape=}")
        logger.debug(f"{v_dims=}")
        if self.dep_indices is None:
            logger.debug(f"{self.dep_indices=}")
        else:
            logger.debug(f"{self.dep_indices.shape=}")
        logger.debug(f"{dep_indices.shape=}")
        logger.debug(f"{mask_update=}")

        mask_shape = tuple(v_dims[::-1])
        if self.mask is None or self.mask.shape != mask_shape:
            logger.info("Allocating a new mask array...")
            self.mask = np.empty(mask_shape, np.uint8)

        if mask_update == MaskUpdate.PARTIAL:
            logger.info("Starting a partial mask update...")
            assert self.dep_indices is not None, \
                "dep_indices not previously set."
            assert self.dep_indices.shape == dep_indices.shape, \
                "dep_indices not the same shape as the previous array."
            if axis == 0:
                for i in range(i_dims[0]):
                    for j in range(i_dims[1]):
                        a = self.dep_indices[j, i]
                        b = dep_indices[j, i]
                        if a < b:
                            self.mask[j, i, a:b] = fill_below
                        else:
                            self.mask[j, i, b:a] = fill_above
            elif axis == 1:
                for i in range(i_dims[0]):
                    for j in range(i_dims[1]):
                        a = self.dep_indices[j, i]
                        b = dep_indices[j, i]
                        if a < b:
                            self.mask[j, a:b, i] = fill_below
                        else:
                            self.mask[j, b:a, i] = fill_above
            elif axis == 2:
                for i in range(i_dims[0]):
                    for j in range(i_dims[1]):
                        a = self.dep_indices[j, i]
                        b = dep_indices[j, i]
                        if a < b:
                            self.mask[a:b, j, i] = fill_below
                        else:
                            self.mask[b:a, j, i] = fill_above
            else:
                raise RuntimeError(f"Axis {axis} not in [0, 1, 2].")
        elif mask_update == MaskUpdate.FULL:
            logger.info("Starting a full mask update...")
            # This is a very slow loop, on the order of 0.4 seconds. Ideally, it
            # would be written in C++ for drastic speed-up, or, even better,
            # pushed to the GPU.
            if axis == 0:
                for i in range(i_dims[0]):
                    for j in range(i_dims[1]):
                        self.mask[j, i, :dep_indices[j, i]] = fill_below
                        self.mask[j, i, dep_indices[j, i]:] = fill_above
            elif axis == 1:
                for i in range(i_dims[0]):
                    for j in range(i_dims[1]):
                        self.mask[j, :dep_indices[j, i], i] = fill_below
                        self.mask[j, dep_indices[j, i]:, i] = fill_above
            elif axis == 2:
                for i in range(i_dims[0]):
                    for j in range(i_dims[1]):
                        self.mask[:dep_indices[j, i], j, i] = fill_below
                        self.mask[dep_indices[j, i]:, j, i] = fill_above
            else:
                raise RuntimeError(f"Axis {axis} not in [0, 1, 2].")
        else:
            raise RuntimeError(f"Unexpected value for mask_update: {mask_update}.")

        logger.info("Mask generated.")

        # Update the cache.
        self.dep_indices = dep_indices

        return self.mask

    def get_vtk(self) -> vtkImageData:
        """Produce a 3D VTK data object for the mask array and return it.

        Operates on the MaskUpdater thread.

        Masks require vtkImageData rather than the vtkImageImporter for volumes.
        """

        assert self.has_volume(), "Must call set_volume first."

        # Only one thread is allowed to generate masks at a time.
        with self.get_vtk_lock:
            mask = self._make_mask()
            vtk_array = vtkDataArray.CreateDataArray(VTK_UNSIGNED_CHAR)
            vtk_array.SetNumberOfComponents(1)
            vtk_array.SetNumberOfTuples(mask.size)
            vtk_array.SetVoidArray(mask.ravel(), mask.size, 1)

            self.vtk_data = vtkImageData()
            self.vtk_data.SetDimensions(mask.shape[::-1])
            self.vtk_data.GetPointData().SetScalars(vtk_array)
            # By keeping a handle to the underlying array data, we can avoid
            # VTK access violations related to premature garbage collection.
            self.vtk_data._array_data = mask
            return self.vtk_data


# noinspection PyPep8Naming
def _radial_distance(
        X: npt.NDArray[np.float32],
        ctrl_ind: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    """Compute the pairwise radial distances of the given points to the
    control points.

    Definition:
      phi(r) = r^2 * log(r)
      Where "r" is the distance between the control point and the data point.

    Args:
      X (array): n points in the source space. Shape: (n, 2)
      ctrl_ind (array): n_c control points representing the independent
      variables. Shape: (n_c, 2)

    Returns:
      array: The radial distance for each point to a control point
      (phi(X)) Shape: (n, n_c)
    """

    dist_sq = cdist(X, ctrl_ind, metric="sqeuclidean")
    dist_sq = dist_sq.astype(np.float32)
    dist_sq[dist_sq == 0] = 1  # phi(0) = 0 by definition.
    return dist_sq * np.log(dist_sq) / 2


def _make_grid_axes(
        lower: npt.NDArray[np.float32],
        upper: npt.NDArray[np.float32],
        dims: Sequence[int]) -> (npt.NDArray[np.float32], npt.NDArray[np.float32]):
    """Create the two orthogonal vectors that make up the point grid.

    :param lower: The lower bounds for the two independent variable axes.
    :param upper: The upper bounds for the two independent variable axes.
    :param dims: The size of the mask along the two independent variable axes.
    :return: Two vectors of shape (1, dims[0]), and  with
        interpolated values between lower and upper.
    """

    # The two independent axes in the world space make the grid.
    a0 = np.linspace(lower[0], upper[0], dims[0], dtype=np.float32)
    a1 = np.linspace(lower[1], upper[1], dims[1], dtype=np.float32)
    a1, a0 = np.ix_(a1, a0)
    return a0, a1


def _make_dep_var(
        a0: npt.NDArray[np.float32],
        a1: npt.NDArray[np.float32],
        parameters: npt.NDArray[np.float32],
        i_ctrl: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    """Compose the grid and evaluate the 2D spline for each point in it.

    :param a0: The 1st array describing the points grid. Shape: (1, i_dims[0])
    :param a1: The 2nd array describing the points grid. Shape: (i_dims[1], 1)
    :param parameters: The thin plate spline parameters.
    :param i_ctrl: The control array along the independent variable directions.
    :return: A 2D array of values representing the dependent variable.
    """

    # Resample the mesh grid as a series of points.
    p = np.empty((a1.shape[0], a0.shape[1], 2), dtype=np.float32)
    p[:, :, 0] = a0
    p[:, :, 1] = a1
    p = p.reshape((-1, 2))

    # Compute the dependent variable.
    phi = _radial_distance(p, i_ctrl)
    phi_1p = np.hstack((phi, np.ones((p.shape[0], 1)), p))
    dep_var = (phi_1p @ parameters).reshape((a1.shape[0], a0.shape[1]))
    return dep_var
