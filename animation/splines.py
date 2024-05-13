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

import numpy as np
from scipy.spatial.distance import cdist


# noinspection PyPep8Naming
class CylinderSpline:
    """Copied from the package thin-plate-spline and modified to use a distance
    function compatible with cylindrical coordinates.

    The two key differences are:
    1. The distance metric for X[:, 1] wraps around such that 0 = 1.
    2. There is no linear component parameter for X[:, 1].
    """

    def __init__(self, smoothness: float = 0., height_diameter_ratio: float = 1.) -> None:
        self._fitted = False
        self.alpha = smoothness
        self.HDrat = height_diameter_ratio
        self.parameters = np.array([], dtype=np.float32)
        self.control_points = np.array([], dtype=np.float32)

    def fit(self, X: np.ndarray, Y: np.ndarray) -> None:
        n_c = X.shape[0]
        assert Y.shape[0] == n_c
        assert X.shape[1] == 2

        self.control_points = X

        phi = self._radial_distance(X)

        # Build the linear system AP = Y
        X_p = np.hstack([np.ones((n_c, 1)), X[:, 0][:, np.newaxis]])

        A = np.vstack([
            np.hstack([phi + self.alpha * np.identity(n_c), X_p]),
            np.hstack([X_p.T, np.zeros((2, 2))])
        ])

        Y = np.vstack([Y, np.zeros((2, Y.shape[1]))])

        self.parameters = np.linalg.solve(A, Y)
        self._fitted = True

    def transform(self, X: np.ndarray) -> np.ndarray:
        assert self._fitted, "Please call fit first."
        assert X.shape[1] == 2

        phi = self._radial_distance(X)  # n x n_c

        X = np.hstack([phi, np.ones((X.shape[0], 1)), X[:, 0][:, np.newaxis]])  # n x (n_c + d_s)
        return X @ self.parameters

    def _radial_distance(self, X: np.ndarray) -> np.ndarray:
        # noinspection PyUnusedLocal
        def cylinder_surf_dist2(u: np.ndarray, v: np.ndarray) -> np.float64:
            """The distance between two 2D vectors where the first dimension is
            the axial distance and the second is the angular distance on the range [0,1).

            This distance is measured along the surface.

            This metric has an issue in that the derivative is discontinuous
            when two points on diametrically opposed. This leads to issues with
            the fit. It is kept here simply for reference.
            """

            dz = self.HDrat * (u[0] - v[0])
            dt = abs(u[1] - v[1])
            dt = min(dt, 1 - dt)
            return dz*dz + dt*dt

        def cylinder_3D_dist2(u: np.ndarray, v: np.ndarray) -> np.float64:
            """The distance between two 2D vectors where the first dimension is
            the axial distance and the second is the angular distance on the range [0,1).

            This distance is measured between the two points in 3D space for a
            cylinder where R/2 = H = 1. This ratio can be adjusted to change how
            the spline's curvature is weighed between its two dimensions.
            """

            dz = self.HDrat * (u[0] - v[0])
            dt2 = (1 - np.cos(2 * np.pi * (u[1] - v[1]))) / 2
            return dz*dz + dt2

        dist2 = cdist(X, self.control_points, cylinder_3D_dist2)
        dist2[dist2 == 0] = 1  # phi(r) = r^2 log(r) ->  (phi(0) = 0)
        return dist2 * np.log(dist2) / 2


def hermite3(t: float, p0, p1, m0, m1):
    """Interpolate the cubic Hermite spline between `p0` and `p1` with initial
    slope `m0` and final slope `m1` at t on [0, 1]."""

    t2 = t**2
    t3 = t**3
    return (p0 * (2 * t3 - 3 * t2 + 1)
            + m0 * (t3 - 2*t2 + t)
            + p1 * (-2 * t3 + 3 * t2)
            + m1 * (t3 - t2))


def dif_phi(x: np.array, c: np.array) -> np.array:
    """Compute the two spatial derivatives of pairwise radial distance between
    the given points and the control points evaluated at the given points.

    Used for calculating the surface normal of a thin plate spline.

    Definition:
        d/dx phi(r) = d/dx (r^2 * log(r))
        Where "r" is the distance between the control point and the data point.

    :param x: (n, 2) matrix of n points in the source space.
    :param c: (n_c, 2) matrix of n_c control points.

    :return: A 2-tuple of matrices with the change in radial distance between
        each point and a control point (d/dx phi_c(x)). The first is the
        derivative with respect to the variable at index 0, and the second is
        with respect to index 1. Both matrices have shape (n, n_c).
    """

    # r2 is the squared distance, i.e., r^2.
    r2 = cdist(x, c, metric="sqeuclidean")
    r2[r2 == 0] = 1  # Avoid ln(0)
    d_phi_d_var0 = (x[:, 0, None] - c[:, 0, None].T) * (np.log(r2) + 1)
    d_phi_d_var1 = (x[:, 1, None] - c[:, 1, None].T) * (np.log(r2) + 1)
    return d_phi_d_var0, d_phi_d_var1
