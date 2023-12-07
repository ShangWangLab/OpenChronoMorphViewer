import logging
from enum import IntEnum
from threading import Lock
from typing import Optional

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
from timeline import Timeline
from volumeimage import (
    ImageBounds,
    VolumeImage,
)

logger = logging.getLogger(__name__)


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


class Dirty(IntEnum):
    """Enumerates the levels of whole-object dirtiness, or progress
    towards a full mask computation.

    Levels of "dirtiness" in decreasing order:
      0. Timeline/uninitialized: When a totally new set of volumes is loaded and
        everything needs to be reassessed.
      1. Axis: need to reallocate the grid and such when the axis is changed.
      2. Phi: Certain parts of phi are dirty for every control point.
      3. Mask: Just the dependent variable and mask need updating.
      4. Clean: Everything is up-to-date.
    Control points need to partially recalculate phi, but this is separate from dirtiness.
    """
    TIMELINE = 0
    AXIS = 1
    PHI = 2
    MASK = 3
    CLEAN = 4


class VolumeMaskTPS:
    """Stores and calculates the volume mask using a thin-plate spline (TPS).

    Operates an independent thread so that control point updates and such
    can be requested in a non-blocking manner.

    Calculation flow each time a control point is updated:
      Control points -> phi -> dependent variable grid -> resample -> mask
    """

    def __init__(self) -> None:
        self.has_volume: bool = False
        self.axis: int = 0
        self.keep_greater_than: bool = False
        self.regularization: float = 0.
        # The list of control points associated with the UI.
        self.control_points: list[ControlPoint] = []
        # An Nx3 array of points in world space that control the surface.
        # There is a one-to-one correspondence between these and "self.control_points".
        self.control_array: npt.NDArray[np.float32] = np.empty((0, 3), np.float32)
        # Tells whether each control point is "dirty", i.e., has been
        # changed since phi was last calculated.
        self.cp_dirty: npt.NDArray[np.bool_] = np.empty((0, 1), np.bool_)
        self.parameters: Optional[npt.NDArray[np.float32]] = None
        self.grid_alloc: Optional[npt.NDArray[np.float32]] = None
        self.phi_alloc: Optional[npt.NDArray[np.float32]] = None
        self.mask_alloc: Optional[npt.NDArray[np.uint8]] = None
        self.vtk_data: Optional[vtkImageData] = None
        self.v_dims: Optional[npt.NDArray[np.uint64]] = None
        self.v_offset: Optional[npt.NDArray[np.float32]] = None
        self.v_scale: Optional[npt.NDArray[np.float32]] = None
        self.lower_bounds: Optional[npt.NDArray[np.float32]] = None
        self.upper_bounds: Optional[npt.NDArray[np.float32]] = None
        self.min_scale: Optional[npt.NDArray[np.float32]] = None
        self.status: Dirty = Dirty.TIMELINE
        self.lock: Lock = Lock()
        # Only one thread is allowed to generate masks at a time.
        self.get_vtk_lock: Lock = Lock()

    def _lower_status(self, new_status: Dirty) -> None:
        """Mark this object as increasingly dirty to at most the level given.

        You must hold "self.lock" while calling this method to avoid race
        conditions.
        """

        self.status = min(self.status, new_status)

    def _raise_status(self, new_status: Dirty) -> None:
        """Mark this object as cleaner to as least the level given.

        You must hold "self.lock" while calling this method to avoid race
        conditions.
        """

        self.status = max(self.status, new_status)

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
                self._lower_status(Dirty.AXIS)
                self.parameters = None
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
                self._lower_status(Dirty.MASK)
            else:
                logger.debug("set_direction deemed unnecessary.")

    def set_regularization(self, regularization: float) -> None:
        """Update the regularization parameter and update the dirtiness.

        Regularization "alpha" or "lambda" varies from [0.0-1.0] and
        determines now closely to track the control points vs. how smoothly
        to fit the surface by reducing the net curvature.

        Thread safe.
        """

        with self.lock:
            logger.debug(f"set_regularization({regularization})")
            if self.regularization != regularization:
                self.regularization = regularization
                # TODO: D_VAR level isn't implemented, but it is the appropriate level.
                self._lower_status(Dirty.AXIS)
                self.parameters = None
            else:
                logger.debug("set_regularization deemed unnecessary.")

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
            new_len = self.control_array.shape[0]
            self.cp_dirty = np.vstack((self.cp_dirty, np.bool_(True)))
            self.parameters = None
            logger.debug(f"cp_dirty: {self.cp_dirty}")

    def delete_cp(self, cp: ControlPoint) -> None:
        """Remove the passed control point and update the dirtiness.

        Fast enough to operate on the UI thread.

        Thread safe.
        """

        with self.lock:
            i = self.control_points.index(cp)
            i_last = self.control_array.shape[0] - 1
            logger.debug(f"Deleting control_point[{i}]. Last index: {i_last}.")
            logger.debug(f"cp_dirty before: {self.cp_dirty}")
            if i != i_last:
                # Swap ...
                logger.debug(f"Control point to delete isn't last.")
                # Replace the deleted row with the last row so we can crop off the end.
                self.control_points[i] = self.control_points[i_last]
                self.control_array[i] = self.control_array[i_last]
                self.cp_dirty[i] = self.cp_dirty[i_last]
            # ... and pop.
            self.control_points.pop()
            self.control_array = self.control_array[:i_last, :]
            self.cp_dirty = self.cp_dirty[:i_last, :]
            self.parameters = None
            self._lower_status(Dirty.AXIS)  # TODO: should be D_VAR
            logger.debug(f"cp_dirty after: {self.cp_dirty}")

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
            self.cp_dirty[i] = np.bool_(True)
            self.parameters = None
            logger.debug(f"cp_dirty after: {self.cp_dirty}")

    def initialize(self, timeline: Timeline) -> None:
        """Find the extents of volumes in the timeline and allocate accordingly.

        Allocate enough memory to store any volume mask and determine the
        extents of the grid, etc.

        Thread safe.
        """

        # Let's hold this lock for the entire duration just in case other
        # methods want to access the variables prior to initialization.
        with self.get_vtk_lock:
            with self.lock:
                logger.info(f"Initializing...")
                extreme_bounds: ImageBounds = timeline.extreme_bounds()
                self.lower_bounds = np.array(extreme_bounds[::2], np.float32)
                self.upper_bounds = np.array(extreme_bounds[1::2], np.float32)
                self.min_scale = np.array(timeline.min_scale(), np.float32)
                max_mask_size: np.uint64 = timeline.max_voxels()
                self.mask_alloc = np.empty((max_mask_size,), np.uint8)
                self.status = Dirty.AXIS
                logger.info(f"Initialized.")

    def uninitialize(self) -> None:
        """Free the memory associated with the mask, etc."""

        with self.get_vtk_lock:
            with self.lock:
                logger.info(f"Uninitializing...")
                self.parameters = None
                self.grid_alloc = None
                self.phi_alloc = None
                self.mask_alloc = None
                self.vtk_data = None
                self.status = Dirty.TIMELINE
                logger.info(f"Uninitialized.")

    def _get_mask(self) -> npt.NDArray[np.uint8]:
        """Generate the mask array.

        Make an appropriately sized view into the allocated mask array and
        fill it with transparent or opaque values depending on whether it is
        above or below the clipping surface defined by the dependent variable.

        You must hold self.gen_VTK_lock while calling this method to avoid
        race conditions.
        """

        # These all need to be set once and they're done. No need to lock.
        assert self.mask_alloc is not None, "Not initialized."
        assert self.lower_bounds is not None, "Not initialized."
        assert self.upper_bounds is not None, "Not initialized."
        assert self.min_scale is not None, "Not initialized."
        assert self.v_dims is not None, "Didn't load a volume."
        assert self.v_offset is not None, "Didn't load a volume."
        assert self.v_scale is not None, "Didn't load a volume."

        with self.lock:
            # Make copies of variables to prevent them from changing during
            # thread operation.
            status: Dirty = self.status
            v_dims = self.v_dims.copy()
            control_array = self.control_array.copy()
            cp_dirty = self.cp_dirty.copy()
            any_cp_dirty = cp_dirty.any()
            axis: int = self.axis
            a_offset = self.v_offset[axis]
            a_scale = self.v_scale[axis]
            a_dim = self.v_dims[axis]

            ia = self._independent_axes()
            i_scale = self.min_scale[ia]
            i_lower_bounds = self.lower_bounds[ia]
            i_upper_bounds = self.upper_bounds[ia]
            i_dims = v_dims[ia]
            # Find the sampling axes for the volume's independent variable
            # grid. Since the bounds are originally in world space,
            # they need to be converted to grid index space.
            i_lower = self.v_offset[ia] - self.lower_bounds[ia]  # world
            i_lower /= self.min_scale[ia]  # world -> indices
            i_step = self.v_scale[ia]  # world
            i_step /= self.min_scale[ia]  # world -> indices
            i_upper = i_lower + i_step * i_dims  # indices

            # This operation is usually computationally cheap enough to lock.
            parameters = self._fit()

            # We can only set these while locked, so let's do them here.
            self.cp_dirty.fill(np.bool_(False))
            self.status = Dirty.CLEAN

        assert status > Dirty.TIMELINE, "Must be initialized before getting the mask."
        logger.info(f"Getting mask. Status: {status}, axis: {axis}")

        # Mask is an appropriately shaped view into the allocated mask.
        mask = self.mask_alloc[:v_dims.prod()].reshape(v_dims[::-1])
        if status >= Dirty.CLEAN and not any_cp_dirty:
            return mask

        # Reset axis - Allocate the new grid for the current axis.
        if status <= Dirty.AXIS:
            logger.info("Resetting axis...")

            # The two independent axes in the full world space make the grid.
            a0 = np.arange(i_lower_bounds[0], i_upper_bounds[0],
                           i_scale[0], dtype=np.float32)
            a1 = np.arange(i_lower_bounds[1], i_upper_bounds[1],
                           i_scale[1], dtype=np.float32)
            a1, a0 = np.ix_(a1, a0)
            # Broadcasting here takes half as long as using meshgrid and
            # stacking.
            self.grid_alloc = np.empty((a1.size, a0.size, 2), dtype=np.float32)
            self.grid_alloc[:, :, 0] = a0
            self.grid_alloc[:, :, 1] = a1

            # Cache phi(r) where 'r' is the distance from each grid point to
            # each control point. Cache extra columns since extending this
            # array is somewhat expensive.
            n_columns = 7 + self.control_array.shape[0]
            self.phi_alloc = np.empty((a1.size, a0.size, n_columns),
                                      dtype=np.float32)
            # Cache the dependent variable as a function of the independent grid.
            self.d_var = np.empty((a1.size, a0.size), dtype=np.float32)
            # Remember which points in the grid have been calculated so we don't
            # need to redo those until they are out of date.
            self.grid_is_dirty = np.ones((a1.size, a0.size), dtype=np.bool_)
            # Since the whole grid is dirty, it is unnecessary to consider the
            # control points as dirty too.
            logger.debug(f"Reset axis dims to {a1.size}x{a0.size}.")
        elif (self.phi_alloc is not None
              and self.phi_alloc.shape[1] < control_array.shape[0]):
            # When additional control points are added, we need to resize the
            # phi cache.
            self.phi_alloc.resize((self.phi_alloc, 7 + control_array.shape[0]))
            logger.debug(f"Resized phi to {self.phi_alloc.shape}")

        a0 = np.arange(i_lower[0], i_upper[0], i_step[0]).astype(np.int_)
        a1 = np.arange(i_lower[1], i_upper[1], i_step[1]).astype(np.int_)
        logger.debug(f"v_offset: {self.v_offset}")
        logger.debug(f"v_scale: {self.v_scale}")
        logger.debug(f"min_scale: {self.min_scale}")
        logger.debug(f"lower_bounds: {self.lower_bounds}")
        logger.debug(f"upper_bounds: {self.upper_bounds}")
        logger.debug(f"dims: {i_dims} of {mask.shape}")
        logger.debug(f"a0: {a0[0]} to {a0[-1]}")
        logger.debug(f"a1: {a1[0]} to {a1[-1]}")
        a1, a0 = np.ix_(a1, a0)

        # Update only the dirty parts of the dependent variable cache.
        # Also update phi as needed based on the grid_is_dirty mask and the
        # cp_dirty mask for the control points.

        assert self.grid_alloc is not None, "Grid was freed unexpectedly."
        assert self.phi_alloc is not None, "Phi was freed unexpectedly."

        if status <= Dirty.PHI or any_cp_dirty:
            logger.info("Updating phi and d_var...")

            # TODO: Temporary for demo:
            if any_cp_dirty:
                self.grid_is_dirty.fill(np.bool_(True))

            # Resample the grid as a series of point indices.
            pi = np.empty((i_dims[1], i_dims[0], 2), dtype=np.int_)
            pi[:, :, 0] = a0
            pi[:, :, 1] = a1
            pi = pi.reshape((-1, 2))

            # TODO: Temporary for demo:
            pid = pi[self.grid_is_dirty[pi[:, 1], pi[:, 0]]]
            pd = self.grid_alloc[pid[:, 1], pid[:, 0]]
            # We can get rid of self.grid_alloc if we replace it with this:
            ##    pd = np.empty(pid.shape, np.float32)
            ##    pd[:, 0] = i_lower_bounds[0] + i_scale[0]*pid[:, 0]
            ##    pd[:, 1] = i_lower_bounds[1] + i_scale[1]*pid[:, 1]

            ctrl_ind = control_array[:, ia]
            phi_d = _radial_distance(pd, ctrl_ind)
            self.grid_is_dirty[pid[:, 1], pid[:, 0]] = np.bool_(False)
            phi_1pd = np.hstack((phi_d, np.ones((pd.shape[0], 1)), pd))
            self.d_var[pid[:, 1], pid[:, 0]] = (phi_1pd @ parameters).ravel()

            ##    phi = self.phi_alloc[:, :, :control_array.shape[0]]
            ##    print("phi_alloc:", self.phi_alloc.shape)
            ##    print("phi:", phi.shape)
            ##
            ##    if any_cp_dirty:
            ##      logger.info("CP dirty; updating clean phi...")
            ##
            ##      # Update only the columns of the previously clean phi points which
            ##      # are associated with the specific dirty control points.
            ##      pic = pi[~self.grid_is_dirty[pi[:, 1], pi[:, 0]]]
            ##      pc = self.grid_alloc[pic[:, 1], pic[:, 0]]
            ##      phi[:, :, cp_dirty.ravel()][pic[:, 1], pic[:, 0], :] = \
            ##        _radial_distance(pc, ctrl_ind[cp_dirty.ravel(), :])
            ##
            ##    # Only the dirty points count now.
            ##    pid = pi[self.grid_is_dirty[pi[:, 1], pi[:, 0]]]
            ##    pd = self.grid_alloc[pid[:, 1], pid[:, 0]]
            ##
            ##    phi_d = _radial_distance(pd, ctrl_ind)
            ##    phi[pid[:, 1], pid[:, 0], :] = phi_d
            ##    self.grid_is_dirty[pid[:, 1], pid[:, 0]] = np.bool_(False)
            ##
            ##    if any_cp_dirty:
            ##      phi_all = phi[pi[:, 1], pi[:, 0], :]
            ##      print("phi_all:", phi_all.shape)
            ##      p_all = self.grid_alloc[pi[:, 1], pi[:, 0]]
            ##      print("p_all:", p_all.shape)
            ##      X = np.hstack((phi_all, np.ones((p_all.shape[0], 1)), p_all))
            ##      print("X:", X.shape)
            ##      self.d_var[pi[:, 1], pi[:, 0]] = (X @ parameters).ravel()
            ##    else:
            ##      print("phi_d:", phi_d.shape)
            ##      X = np.hstack((phi_d, np.ones((pd.shape[0], 1)), pd))
            ##      print("X:", X.shape)
            ##      self.d_var[pid[:, 1], pid[:, 0]] = (X @ parameters).ravel()

            logger.info(f"Phi and d_var updated.")

        # Now set the values of the binary mask.
        logger.info("Generating mask...")

        # Pull this out of the loops.
        if self.keep_greater_than:  # Only accessed once; thread safe.
            fill_below = np.uint8(0)  # Transparent
            fill_above = np.uint8(255)  # Opaque
        else:
            fill_below = np.uint8(255)  # Opaque
            fill_above = np.uint8(0)  # Transparent

        d_indices = np.clip(
            ((self.d_var[a1, a0] - a_offset) / a_scale).astype(np.int_),
            0, a_dim
        )

        # This is a very slow loop, on the order of 0.4 seconds. Ideally, it
        # would be written in C++ for drastic speed-up, or, even better,
        # pushed to the GPU.
        if axis == 0:
            for i in range(i_dims[0]):
                for j in range(i_dims[1]):
                    mask[j, i, :d_indices[j, i]] = fill_below
                    mask[j, i, d_indices[j, i]:] = fill_above
        elif axis == 1:
            for i in range(i_dims[0]):
                for j in range(i_dims[1]):
                    mask[j, :d_indices[j, i], i] = fill_below
                    mask[j, d_indices[j, i]:, i] = fill_above
        elif axis == 2:
            for i in range(i_dims[0]):
                for j in range(i_dims[1]):
                    mask[:d_indices[j, i], j, i] = fill_below
                    mask[d_indices[j, i]:, j, i] = fill_above
        else:
            raise RuntimeError("Axis is outside range(3).")
        logger.info("Mask generated.")
        return mask

    # The constant NxN number of vertices to construct a mesh out of.
    N_MESH: int = 16

    def make_mesh(self) -> vtkActor:
        """Build an actor to represent the surface as a mesh.

        The actor must be added on the UI thread holding the OpenGL context
        or else an error will occur.

        Thread safe.
        """

        # These should be set once and done. No need to lock.
        assert self.v_dims is not None, "Didn't load a volume."
        assert self.v_offset is not None, "Didn't load a volume."
        assert self.v_scale is not None, "Didn't load a volume."

        # Get everything ready so we don't need to access any more
        # attributes that might change on another thread.
        with self.lock:
            axis = self.axis
            ia = self._independent_axes()
            # World coordinates.
            i_lower = self.v_offset[ia]
            i_upper = i_lower + self.v_scale[ia] * self.v_dims[ia]
            parameters = self._fit()
            ctrl_ind = self.control_array[:, ia]

        # The rest of this doesn't need to be locked.
        a0 = np.linspace(i_lower[0], i_upper[0], self.N_MESH)
        a1 = np.linspace(i_lower[1], i_upper[1], self.N_MESH)
        a1, a0 = np.ix_(a1, a0)

        # Resample the mesh grid as a series of points.
        p = np.empty((self.N_MESH, self.N_MESH, 2), dtype=np.float32)
        p[:, :, 0] = a0
        p[:, :, 1] = a1
        p = p.reshape((-1, 2))

        # Compute the dependent variable.
        phi = _radial_distance(p, ctrl_ind)
        phi_1p = np.hstack((phi, np.ones((p.shape[0], 1)), p))
        d_var = (phi_1p @ parameters).reshape((self.N_MESH, self.N_MESH))

        # Make a VTK mesh.
        points = vtkPoints()
        points.SetDataTypeToFloat()
        points.SetNumberOfPoints(self.N_MESH * self.N_MESH)
        if axis == 0:
            for i in range(self.N_MESH):
                for j in range(self.N_MESH):
                    points.SetPoint(i * self.N_MESH + j, d_var[j, i], a0[0, i],
                                    a1[j, 0])
        elif axis == 1:
            for i in range(self.N_MESH):
                for j in range(self.N_MESH):
                    points.SetPoint(i * self.N_MESH + j, a0[0, i], d_var[j, i],
                                    a1[j, 0])
        elif axis == 2:
            for i in range(self.N_MESH):
                for j in range(self.N_MESH):
                    points.SetPoint(i * self.N_MESH + j, a0[0, i], a1[j, 0],
                                    d_var[j, i])
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
            # Shape: XYZ
            assert v_dims.shape == (3,), "'v_dims' must be 3D."
            assert v_offset.shape == (3,), "'v_offset' must be 3D."
            assert v_scale.shape == (3,), "'v_scale' must be 3D."

            same_volume: np.bool_ = np.bool_(
                np.all(v_dims == self.v_dims)
                and np.all(v_offset == self.v_offset)
                and np.all(v_scale == self.v_scale)
            )

            if not same_volume:
                self.v_dims = v_dims
                self.v_offset = v_offset
                self.v_scale = v_scale
                self._lower_status(Dirty.PHI)
            self.has_volume = True

    def get_vtk(self) -> vtkImageData:
        """Produce a 3D VTK data object for the mask array and return it.

        Operates on the MaskUpdater thread.

        Masks require vtkImageData rather than the vtkImageImporter for volumes.
        """

        assert self.v_dims is not None, "Must call set_volume first."

        # Only one thread is allowed to generate masks at a time.
        with self.get_vtk_lock:
            mask = self._get_mask()
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


if __name__ == "__main__":
    # TODO: use this to debug phi
    self = VolumeMaskTPS()
    timeline = Timeline()
    timeline.set_file_paths(
        ["C:/Users/Andyf/Downloads/E5D_09012016/S00_T00.nhdr"]
    )
    self.initialize(timeline)

    # Simulate adding CPs.
    for i in range(3):
        a = np.random.random((3,)).astype(np.float32)
        self.control_array = np.vstack((self.control_array, a))
        self.cp_dirty = np.vstack((self.cp_dirty, True))
    self.control_array *= 600
    self.control_array -= 300
    self._fit()

    # get_VTK:
    volume = timeline.get()

    self.set_volume(volume)
    self.get_vtk()
    self.set_axis(1)
    self.set_direction(False)

    import pdb

    pdb.set_trace()
    self.get_vtk()
